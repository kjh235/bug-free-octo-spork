from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, field_validator

from .models import (
    AgentServiceType,
    CommitmentSource,
    LicenseStatus,
    LicenseType,
    ObligationDomain,
    TaskStatus,
    UserRole,
    VerificationDecision,
)


# ---------------------------------------------------------------------------
# Auth / User
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company_name: str
    role: UserRole


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    company_name: str
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: str | None = None


# ---------------------------------------------------------------------------
# License
# ---------------------------------------------------------------------------

class LicenseCreate(BaseModel):
    license_type: LicenseType
    license_number: str | None = None
    issuing_authority: str | None = None
    jurisdiction: str | None = None   # ISO-like: "US-UT", "US-CA"
    notes: str | None = None
    issued_at: datetime | None = None
    expires_at: datetime | None = None


class LicenseOut(BaseModel):
    id: str
    owner_id: str
    license_type: LicenseType
    license_number: str | None
    issuing_authority: str | None
    jurisdiction: str | None
    original_filename: str | None
    file_hash: str | None
    notes: str | None
    status: LicenseStatus
    issued_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LicenseStatusUpdate(BaseModel):
    status: LicenseStatus


# ---------------------------------------------------------------------------
# Verification Agent
# ---------------------------------------------------------------------------

class VerificationAgentCreate(BaseModel):
    agent_code: str
    name: str
    service_type: AgentServiceType
    domain: ObligationDomain
    coverage: str | None = None
    applicable_jurisdictions: list[str] | None = None
    capabilities: list[str] | None = None
    cost_per_check: float
    response_sla_seconds: int
    accuracy_guarantee: float | None = None
    insurance_amount: float | None = None
    api_endpoint: str | None = None

    @field_validator("cost_per_check")
    @classmethod
    def cost_must_be_nonnegative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("cost_per_check must be >= 0")
        return v


class VerificationAgentOut(BaseModel):
    id: str
    agent_code: str
    name: str
    service_type: AgentServiceType
    domain: ObligationDomain
    coverage: str | None
    applicable_jurisdictions: list[str] | None
    capabilities: list[str] | None
    cost_per_check: float
    response_sla_seconds: int
    accuracy_guarantee: float | None
    insurance_amount: float | None
    api_endpoint: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Obligation
# ---------------------------------------------------------------------------

class ObligationCreate(BaseModel):
    obligation_code: str
    title: str
    description: str | None = None
    domain: ObligationDomain
    jurisdiction: str | None = None
    required_license_type: LicenseType | None = None
    violation_action: str = "shipment_rejected"
    penalty_amount: float | None = None
    is_blocking: bool = True


class ObligationOut(BaseModel):
    id: str
    obligation_code: str
    title: str
    description: str | None
    domain: ObligationDomain
    jurisdiction: str | None
    required_license_type: LicenseType | None
    violation_action: str
    penalty_amount: float | None
    is_blocking: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Commitment
# ---------------------------------------------------------------------------

class CommitmentCreate(BaseModel):
    commitment_code: str
    obligation_id: str
    title: str
    description: str | None = None
    source: CommitmentSource
    agent_id: str | None = None  # required when source=outsourced
    is_preferred: bool = False


class CommitmentOut(BaseModel):
    id: str
    commitment_code: str
    obligation_id: str
    title: str
    description: str | None
    source: CommitmentSource
    agent_id: str | None
    is_preferred: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Verification Task
# ---------------------------------------------------------------------------

class VerificationTaskCreate(BaseModel):
    license_id: str
    obligation_id: str  # resolver picks the preferred commitment + agent


class VerificationTaskOut(BaseModel):
    id: str
    task_code: str
    license_id: str
    commitment_id: str
    agent_id: str | None
    requester_id: str
    status: TaskStatus
    is_blocking: bool
    due_at: datetime | None
    request_payload: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Verification Result
# ---------------------------------------------------------------------------

class VerificationResultCreate(BaseModel):
    """Used by internal team to record a manual result."""
    task_id: str
    decision: VerificationDecision
    confidence: float | None = None
    evidence: dict[str, Any] | None = None
    notes: str | None = None
    actual_cost: float | None = None
    invoice_id: str | None = None


class VerificationResultOut(BaseModel):
    id: str
    task_id: str
    decision: VerificationDecision
    confidence: float | None
    evidence: dict[str, Any] | None
    notes: str | None
    actual_cost: float | None
    invoice_id: str | None
    verified_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Resolver / Orchestration
# ---------------------------------------------------------------------------

class ResolveRequest(BaseModel):
    """Request to resolve obligations for a shipment and generate verification tasks."""
    license_ids: list[str]
    obligation_codes: list[str]


class ResolveResult(BaseModel):
    tasks_created: list[VerificationTaskOut]
    total_estimated_cost: float
    max_sla_seconds: int
    agent_summary: list[dict[str, Any]]


class ShipmentVerificationStatus(BaseModel):
    """Aggregated verification status for a set of tasks."""
    all_passed: bool
    tasks: list[VerificationTaskOut]
    results: list[VerificationResultOut]
    total_cost: float
    audit_log: list[dict[str, Any]]
