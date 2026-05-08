from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import Commitment, Obligation
from ..schemas import CommitmentCreate, CommitmentOut, ObligationCreate, ObligationOut

router = APIRouter(prefix="/obligations", tags=["obligations"])


# ---------------------------------------------------------------------------
# Obligations
# ---------------------------------------------------------------------------

@router.post("/", response_model=ObligationOut, status_code=status.HTTP_201_CREATED)
def create_obligation(
    body: ObligationCreate,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> Obligation:
    if db.query(Obligation).filter(Obligation.obligation_code == body.obligation_code).first():
        raise HTTPException(status_code=400, detail="Obligation code already exists")
    obligation = Obligation(**body.model_dump())
    db.add(obligation)
    db.commit()
    db.refresh(obligation)
    return obligation


@router.get("/", response_model=list[ObligationOut])
def list_obligations(
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> list[Obligation]:
    return db.query(Obligation).filter(Obligation.is_active == True).all()  # noqa: E712


@router.get("/{obligation_id}", response_model=ObligationOut)
def get_obligation(
    obligation_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> Obligation:
    ob = db.get(Obligation, obligation_id)
    if not ob:
        raise HTTPException(status_code=404, detail="Obligation not found")
    return ob


# ---------------------------------------------------------------------------
# Commitments (nested under obligations)
# ---------------------------------------------------------------------------

@router.post("/commitments", response_model=CommitmentOut, status_code=status.HTTP_201_CREATED)
def create_commitment(
    body: CommitmentCreate,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> Commitment:
    if not db.get(Obligation, body.obligation_id):
        raise HTTPException(status_code=404, detail="Obligation not found")
    if db.query(Commitment).filter(Commitment.commitment_code == body.commitment_code).first():
        raise HTTPException(status_code=400, detail="Commitment code already exists")
    commitment = Commitment(**body.model_dump())
    db.add(commitment)
    db.commit()
    db.refresh(commitment)
    return commitment


@router.get("/commitments/all", response_model=list[CommitmentOut])
def list_commitments(
    obligation_id: str | None = None,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> list[Commitment]:
    q = db.query(Commitment).filter(Commitment.is_active == True)  # noqa: E712
    if obligation_id:
        q = q.filter(Commitment.obligation_id == obligation_id)
    return q.all()


@router.get("/commitments/{commitment_id}", response_model=CommitmentOut)
def get_commitment(
    commitment_id: str,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_user),
) -> Commitment:
    c = db.get(Commitment, commitment_id)
    if not c:
        raise HTTPException(status_code=404, detail="Commitment not found")
    return c
