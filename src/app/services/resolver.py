"""
Resolver: maps obligations to the best commitment + agent for a given license.

Step 7.5 from the architecture doc:
  For each obligation:
    1. Find active commitments linked to the obligation
    2. Prefer outsourced when an active agent exists and is preferred
    3. Fall back to internal commitment
    4. Return (commitment, agent | None) pairs
"""
from sqlalchemy.orm import Session

from ..models import Commitment, CommitmentSource, License, Obligation, VerificationAgent


def resolve_commitment(
    obligation: Obligation,
    db: Session,
) -> tuple[Commitment, VerificationAgent | None]:
    """
    Return the best (commitment, agent) pair for an obligation.
    Raises ValueError when no active commitment exists.
    """
    commitments = (
        db.query(Commitment)
        .filter(
            Commitment.obligation_id == obligation.id,
            Commitment.is_active == True,  # noqa: E712
        )
        .all()
    )
    if not commitments:
        raise ValueError(f"No active commitments for obligation {obligation.obligation_code!r}")

    # prefer commitments marked preferred; among those prefer outsourced
    preferred = [c for c in commitments if c.is_preferred]
    pool = preferred if preferred else commitments

    # pick the outsourced one if available (cheaper, faster)
    outsourced = [c for c in pool if c.source == CommitmentSource.outsourced and c.agent_id]
    chosen = outsourced[0] if outsourced else pool[0]

    agent: VerificationAgent | None = None
    if chosen.agent_id:
        agent = db.get(VerificationAgent, chosen.agent_id)
        if agent and not agent.is_active:
            agent = None  # agent deactivated; fall through to internal

    return chosen, agent


def build_agent_payload(license_: License, obligation: Obligation) -> dict:
    """Construct the payload to send to a verification agent API."""
    return {
        "licenseId": license_.id,
        "licenseNumber": license_.license_number,
        "licenseType": license_.license_type.value,
        "jurisdiction": license_.jurisdiction,
        "holderCompany": license_.owner.company_name if license_.owner else None,
        "obligationCode": obligation.obligation_code,
        "domain": obligation.domain.value,
        "documentHash": license_.file_hash,
    }
