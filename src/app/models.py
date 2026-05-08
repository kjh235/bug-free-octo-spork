"""
SQLAlchemy ORM models for the logistics license verification system.

Domain:
  User            — shipper, carrier, or recipient party
  License         — credential document uploaded by a party
  VerificationAgent — registry entry for an internal or third-party verifier
  Obligation      — regulatory requirement (e.g. "verify UT alcohol license")
  Commitment      — fulfillment policy: internal team or specific agent
  VerificationTask — work item: verify a specific license under a commitment
  VerificationResult — recorded outcome (PASS/FAIL/SLA_EXCEEDED) with evidence
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    shipper = "shipper"
    carrier = "carrier"
    recipient = "recipient"


class LicenseType(str, enum.Enum):
    # carrier
    operating_authority = "operating_authority"
    dot_registration = "dot_registration"
    hazmat_carrier_cert = "hazmat_carrier_cert"
    vehicle_permit = "vehicle_permit"
    # shipper
    export_license = "export_license"
    hazmat_shipper_cert = "hazmat_shipper_cert"
    customs_broker = "customs_broker"
    alcohol_shipper = "alcohol_shipper"
    # recipient
    import_license = "import_license"
    delivery_authorization = "delivery_authorization"
    # general
    business_registration = "business_registration"
    other = "other"


class LicenseStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"
    expired = "expired"


class AgentServiceType(str, enum.Enum):
    third_party_verification = "third-party-verification"
    government_database = "government-database-access"
    internal_team = "internal-team"


class CommitmentSource(str, enum.Enum):
    internal = "internal"
    outsourced = "outsourced"


class ObligationDomain(str, enum.Enum):
    alcohol_shipping = "alcohol-shipping"
    hazmat = "hazmat"
    customs_trade = "customs-trade"
    ofac_sanctions = "ofac-sanctions"
    carrier_authority = "carrier-authority"
    general = "general"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    sla_exceeded = "sla_exceeded"


class VerificationDecision(str, enum.Enum):
    pass_ = "PASS"
    fail = "FAIL"
    info_missing = "INFO_MISSING"
    sla_exceeded = "SLA_EXCEEDED"
    error = "ERROR"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    licenses: Mapped[list["License"]] = relationship(
        "License", back_populates="owner", foreign_keys="License.owner_id"
    )
    tasks_requested: Mapped[list["VerificationTask"]] = relationship(
        "VerificationTask", back_populates="requester", foreign_keys="VerificationTask.requester_id"
    )


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    license_type: Mapped[LicenseType] = mapped_column(Enum(LicenseType), nullable=False)
    license_number: Mapped[str | None] = mapped_column(String, nullable=True)
    issuing_authority: Mapped[str | None] = mapped_column(String, nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. "US-UT"
    # local path to uploaded file (relative to uploads root)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String, nullable=True)  # sha256 for audit
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LicenseStatus] = mapped_column(
        Enum(LicenseStatus), default=LicenseStatus.pending, nullable=False
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    owner: Mapped["User"] = relationship("User", back_populates="licenses", foreign_keys=[owner_id])
    tasks: Mapped[list["VerificationTask"]] = relationship(
        "VerificationTask", back_populates="license"
    )


class VerificationAgent(Base):
    """
    Registry of verifiers: third-party APIs, government databases, or internal teams.
    Mirrors the verificationAgentRegistry in the architecture doc.
    """
    __tablename__ = "verification_agents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_uuid)
    agent_code: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    service_type: Mapped[AgentServiceType] = mapped_column(Enum(AgentServiceType), nullable=False)
    domain: Mapped[ObligationDomain] = mapped_column(Enum(ObligationDomain), nullable=False)
    coverage: Mapped[str | None] = mapped_column(String, nullable=True)       # e.g. "all-50-states"
    applicable_jurisdictions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)    # list of check names
    cost_per_check: Mapped[float] = mapped_column(Float, nullable=False)
    response_sla_seconds: Mapped[int] = mapped_column(Integer, nullable=False) # SLA in seconds
    accuracy_guarantee: Mapped[float | None] = mapped_column(Float, nullable=True)
    insurance_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    api_endpoint: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    commitments: Mapped[list["Commitment"]] = relationship(
        "Commitment", back_populates="agent"
    )
    tasks: Mapped[list["VerificationTask"]] = relationship(
        "VerificationTask", back_populates="agent"
    )


class Obligation(Base):
    """
    A regulatory requirement that must be met before a shipment proceeds.
    E.g. "Verify shipper holds valid alcohol license in destination jurisdiction."
    """
    __tablename__ = "obligations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_uuid)
    obligation_code: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[ObligationDomain] = mapped_column(Enum(ObligationDomain), nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String, nullable=True)
    required_license_type: Mapped[LicenseType | None] = mapped_column(Enum(LicenseType), nullable=True)
    # enforcement config
    violation_action: Mapped[str] = mapped_column(String, default="shipment_rejected")
    penalty_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_blocking: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    commitments: Mapped[list["Commitment"]] = relationship(
        "Commitment", back_populates="obligation"
    )


class Commitment(Base):
    """
    Policy for fulfilling an obligation: use internal team or outsource to an agent.
    Multiple commitments can exist per obligation (internal vs. outsourced alternatives).
    """
    __tablename__ = "commitments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_uuid)
    commitment_code: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    obligation_id: Mapped[str] = mapped_column(ForeignKey("obligations.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[CommitmentSource] = mapped_column(Enum(CommitmentSource), nullable=False)
    # null when source=internal (handled by internal team)
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("verification_agents.id"), nullable=True, index=True
    )
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    obligation: Mapped["Obligation"] = relationship("Obligation", back_populates="commitments")
    agent: Mapped["VerificationAgent | None"] = relationship(
        "VerificationAgent", back_populates="commitments"
    )
    tasks: Mapped[list["VerificationTask"]] = relationship(
        "VerificationTask", back_populates="commitment"
    )


class VerificationTask(Base):
    """
    Work item: verify a specific license, under a specific commitment, via a specific agent.
    Tracks the full lifecycle from creation through execution to result.
    """
    __tablename__ = "verification_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_uuid)
    task_code: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    license_id: Mapped[str] = mapped_column(ForeignKey("licenses.id"), nullable=False, index=True)
    commitment_id: Mapped[str] = mapped_column(ForeignKey("commitments.id"), nullable=False, index=True)
    # agent resolved at task creation (may be null for internal)
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("verification_agents.id"), nullable=True, index=True
    )
    # who initiated the verification request
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.pending)
    is_blocking: Mapped[bool] = mapped_column(Boolean, default=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # payload sent to agent API
    request_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    license: Mapped["License"] = relationship("License", back_populates="tasks")
    commitment: Mapped["Commitment"] = relationship("Commitment", back_populates="tasks")
    agent: Mapped["VerificationAgent | None"] = relationship(
        "VerificationAgent", back_populates="tasks"
    )
    requester: Mapped["User"] = relationship("User", back_populates="tasks_requested")
    result: Mapped["VerificationResult | None"] = relationship(
        "VerificationResult", back_populates="task", uselist=False
    )


class VerificationResult(Base):
    """
    Recorded outcome of a VerificationTask.
    Captures decision, evidence, cost, and full audit data.
    """
    __tablename__ = "verification_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_uuid)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("verification_tasks.id"), unique=True, nullable=False, index=True
    )
    decision: Mapped[VerificationDecision] = mapped_column(Enum(VerificationDecision), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # structured evidence returned by agent (license_exists, not_expired, holder_match, etc.)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    invoice_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # raw agent response for audit
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped["VerificationTask"] = relationship("VerificationTask", back_populates="result")
