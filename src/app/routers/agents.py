from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import ObligationDomain, VerificationAgent
from ..schemas import VerificationAgentCreate, VerificationAgentOut

router = APIRouter(prefix="/agents", tags=["verification-agents"])


@router.post("/", response_model=VerificationAgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(
    body: VerificationAgentCreate,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> VerificationAgent:
    if db.query(VerificationAgent).filter(VerificationAgent.agent_code == body.agent_code).first():
        raise HTTPException(status_code=400, detail="Agent code already exists")
    agent = VerificationAgent(**body.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/", response_model=list[VerificationAgentOut])
def list_agents(
    domain: ObligationDomain | None = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> list[VerificationAgent]:
    q = db.query(VerificationAgent)
    if active_only:
        q = q.filter(VerificationAgent.is_active == True)  # noqa: E712
    if domain:
        q = q.filter(VerificationAgent.domain == domain)
    return q.order_by(VerificationAgent.cost_per_check).all()


@router.get("/{agent_id}", response_model=VerificationAgentOut)
def get_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> VerificationAgent:
    agent = db.get(VerificationAgent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}/deactivate", response_model=VerificationAgentOut)
def deactivate_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> VerificationAgent:
    agent = db.get(VerificationAgent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.is_active = False
    db.commit()
    db.refresh(agent)
    return agent
