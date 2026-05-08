"""
Verification Tasks router.

POST /tasks/resolve  — resolver: take a list of (license_id, obligation_code) pairs,
                        pick commitments + agents, create tasks, auto-execute outsourced ones.
GET  /tasks/         — list tasks (filtered by license, status, etc.)
GET  /tasks/{id}     — single task
POST /results/       — record a manual result for internal-team tasks
GET  /results/{id}   — single result
GET  /tasks/{id}/status — aggregated shipment-level verdict
"""
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import (
    Commitment,
    License,
    Obligation,
    TaskStatus,
    User,
    VerificationDecision,
    VerificationResult,
    VerificationTask,
)
from ..schemas import (
    ResolveRequest,
    ResolveResult,
    ShipmentVerificationStatus,
    VerificationResultCreate,
    VerificationResultOut,
    VerificationTaskOut,
)
from ..services.executor import execute_tasks_parallel, record_result
from ..services.resolver import build_agent_payload, resolve_commitment

router = APIRouter(tags=["tasks"])

_TASK_COUNTER = 0


def _next_task_code() -> str:
    global _TASK_COUNTER
    _TASK_COUNTER += 1
    return f"TASK-{_TASK_COUNTER:06d}"


# ---------------------------------------------------------------------------
# Resolve: create tasks for a set of license + obligation pairs
# ---------------------------------------------------------------------------

@router.post("/tasks/resolve", response_model=ResolveResult, status_code=status.HTTP_201_CREATED)
async def resolve_and_create_tasks(
    body: ResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResolveResult:
    created_tasks: list[VerificationTask] = []

    for license_id in body.license_ids:
        license_ = db.get(License, license_id)
        if not license_:
            raise HTTPException(status_code=404, detail=f"License {license_id!r} not found")
        # eagerly load owner for payload building
        _ = license_.owner

        for ob_code in body.obligation_codes:
            ob = db.query(Obligation).filter(Obligation.obligation_code == ob_code).first()
            if not ob:
                raise HTTPException(status_code=404, detail=f"Obligation {ob_code!r} not found")

            try:
                commitment, agent = resolve_commitment(ob, db)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))

            payload = build_agent_payload(license_, ob)
            sla_seconds = agent.response_sla_seconds if agent else 0
            task = VerificationTask(
                task_code=_next_task_code(),
                license_id=license_id,
                commitment_id=commitment.id,
                agent_id=agent.id if agent else None,
                requester_id=current_user.id,
                is_blocking=ob.is_blocking,
                due_at=datetime.now(timezone.utc) + timedelta(seconds=sla_seconds) if sla_seconds else None,
                request_payload=payload,
            )
            db.add(task)
            db.flush()  # get task.id before commit
            if agent:
                task.agent = agent  # attach relationship for executor
            created_tasks.append(task)

    db.commit()
    for t in created_tasks:
        db.refresh(t)

    # auto-execute outsourced tasks in parallel
    outsourced = [t for t in created_tasks if t.agent_id]
    if outsourced:
        await execute_tasks_parallel(outsourced, db)

    total_cost = sum(
        t.agent.cost_per_check for t in created_tasks if t.agent
    )
    max_sla = max(
        (t.agent.response_sla_seconds for t in created_tasks if t.agent),
        default=0,
    )
    agent_summary = [
        {
            "agent": t.agent.name if t.agent else "Internal Team",
            "task_code": t.task_code,
            "cost": t.agent.cost_per_check if t.agent else 0,
            "sla_seconds": t.agent.response_sla_seconds if t.agent else None,
        }
        for t in created_tasks
    ]

    return ResolveResult(
        tasks_created=[VerificationTaskOut.model_validate(t) for t in created_tasks],
        total_estimated_cost=total_cost,
        max_sla_seconds=max_sla,
        agent_summary=agent_summary,
    )


# ---------------------------------------------------------------------------
# Tasks CRUD
# ---------------------------------------------------------------------------

@router.get("/tasks/", response_model=list[VerificationTaskOut])
def list_tasks(
    license_id: str | None = None,
    status_filter: TaskStatus | None = None,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> list[VerificationTask]:
    q = db.query(VerificationTask)
    if license_id:
        q = q.filter(VerificationTask.license_id == license_id)
    if status_filter:
        q = q.filter(VerificationTask.status == status_filter)
    return q.order_by(VerificationTask.created_at.desc()).all()


@router.get("/tasks/{task_id}", response_model=VerificationTaskOut)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> VerificationTask:
    task = db.get(VerificationTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ---------------------------------------------------------------------------
# Results (manual submission for internal-team tasks)
# ---------------------------------------------------------------------------

@router.post("/results/", response_model=VerificationResultOut, status_code=status.HTTP_201_CREATED)
def submit_result(
    body: VerificationResultCreate,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> VerificationResult:
    task = db.get(VerificationTask, body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.result:
        raise HTTPException(status_code=409, detail="Result already recorded for this task")

    result = record_result(
        task,
        {
            "result": body.decision.value,
            "confidence": body.confidence,
            "evidence": body.evidence,
            "cost": body.actual_cost,
            "invoice_id": body.invoice_id,
            "error": body.notes,
            "raw": None,
        },
        db,
    )
    # reflect verified status on license
    if body.decision == VerificationDecision.pass_:
        from ..models import LicenseStatus
        task.license.status = LicenseStatus.verified
        db.commit()
    return result


@router.get("/results/{result_id}", response_model=VerificationResultOut)
def get_result(
    result_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> VerificationResult:
    result = db.get(VerificationResult, result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    return result


# ---------------------------------------------------------------------------
# Aggregated shipment status
# ---------------------------------------------------------------------------

@router.get("/tasks/shipment-status", response_model=ShipmentVerificationStatus)
def shipment_status(
    license_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> ShipmentVerificationStatus:
    tasks = (
        db.query(VerificationTask)
        .filter(VerificationTask.license_id == license_id)
        .all()
    )
    results = [t.result for t in tasks if t.result]
    all_passed = all(
        r.decision == VerificationDecision.pass_ for r in results
    ) and len(results) == len(tasks)
    total_cost = sum(r.actual_cost or 0 for r in results)

    audit_log = [
        {
            "task_code": t.task_code,
            "agent": t.agent.name if t.agent else "Internal Team",
            "result": t.result.decision.value if t.result else "PENDING",
            "cost": t.result.actual_cost if t.result else None,
            "verified_at": t.result.verified_at.isoformat() if t.result else None,
            "evidence": t.result.evidence if t.result else None,
        }
        for t in tasks
    ]

    return ShipmentVerificationStatus(
        all_passed=all_passed,
        tasks=[VerificationTaskOut.model_validate(t) for t in tasks],
        results=[VerificationResultOut.model_validate(r) for r in results],
        total_cost=total_cost,
        audit_log=audit_log,
    )
