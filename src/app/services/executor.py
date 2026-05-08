"""
Executor: calls a third-party verification agent API and records the result.

Mirrors the VerificationExecutor in the architecture doc.
In production, replace the stub HTTP call with real httpx calls to agent APIs.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import (
    TaskStatus,
    VerificationDecision,
    VerificationResult,
    VerificationTask,
)


async def call_agent(
    task: VerificationTask,
    api_endpoint: str,
    api_key: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    """
    POST task.request_payload to the agent API.
    Returns a normalised dict with keys: result, confidence, evidence, cost, raw.
    On timeout or error, returns a failure dict without raising.
    """
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                api_endpoint,
                json=task.request_payload,
                headers=headers,
            )
            response.raise_for_status()
            body = response.json()
            return {
                "result": body.get("result", "PASS"),
                "confidence": body.get("confidence"),
                "evidence": body.get("evidence"),
                "cost": body.get("cost"),
                "invoice_id": body.get("invoiceId"),
                "raw": body,
                "error": None,
            }
    except asyncio.TimeoutError:
        return {
            "result": VerificationDecision.sla_exceeded.value,
            "confidence": None,
            "evidence": None,
            "cost": None,
            "invoice_id": None,
            "raw": None,
            "error": f"Agent exceeded {timeout_seconds}s SLA",
        }
    except Exception as exc:
        return {
            "result": VerificationDecision.error.value,
            "confidence": None,
            "evidence": None,
            "cost": None,
            "invoice_id": None,
            "raw": None,
            "error": str(exc),
        }


def record_result(
    task: VerificationTask,
    agent_response: dict[str, Any],
    db_session: Any,
) -> VerificationResult:
    """Persist the result and update task status."""
    raw_result = agent_response.get("result", VerificationDecision.error.value)
    try:
        decision = VerificationDecision(raw_result)
    except ValueError:
        decision = VerificationDecision.error

    result = VerificationResult(
        task_id=task.id,
        decision=decision,
        confidence=agent_response.get("confidence"),
        evidence=agent_response.get("evidence"),
        notes=agent_response.get("error"),
        actual_cost=agent_response.get("cost"),
        invoice_id=agent_response.get("invoice_id"),
        raw_response=agent_response.get("raw"),
    )

    task.status = (
        TaskStatus.completed
        if decision in (VerificationDecision.pass_, VerificationDecision.fail)
        else TaskStatus.failed
    )
    task.completed_at = datetime.now(timezone.utc)

    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)
    return result


async def execute_tasks_parallel(
    tasks: list[VerificationTask],
    db_session: Any,
    api_key_lookup: dict[str, str] | None = None,
) -> list[VerificationResult]:
    """
    Execute multiple verification tasks concurrently (architecture doc: Pattern 4).
    api_key_lookup maps agent_id → api_key; in production pull from vault.
    """
    api_key_lookup = api_key_lookup or {}

    async def _run_one(task: VerificationTask) -> VerificationResult:
        task.status = TaskStatus.in_progress
        task.started_at = datetime.now(timezone.utc)
        db_session.commit()

        if task.agent and task.agent.api_endpoint:
            response = await call_agent(
                task=task,
                api_endpoint=task.agent.api_endpoint,
                api_key=api_key_lookup.get(task.agent_id or ""),
                timeout_seconds=task.agent.response_sla_seconds,
            )
        else:
            # internal team — result must be submitted manually via POST /results
            task.status = TaskStatus.pending
            db_session.commit()
            return None  # type: ignore[return-value]

        return record_result(task, response, db_session)

    results = await asyncio.gather(*[_run_one(t) for t in tasks])
    return [r for r in results if r is not None]
