"""Pydantic models for the QueueStorm Investigator API.

These mirror the official problem statement (problem.md, sections 5-7) exactly.
Enum values are spelled EXACTLY as the spec requires — any case/plural/spelling
drift is scored as a schema violation, so they live here as ``Literal`` types and
nowhere else.
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enum vocabularies (single source of truth — imported by the reasoning engine)
# ---------------------------------------------------------------------------

Language = Literal["en", "bn", "mixed"]
Channel = Literal["in_app_chat", "call_center", "email", "merchant_portal", "field_agent"]
UserType = Literal["customer", "merchant", "agent", "unknown"]
TransactionType = Literal["transfer", "payment", "cash_in", "cash_out", "settlement", "refund"]
TransactionStatus = Literal["completed", "failed", "pending", "reversed"]

EvidenceVerdict = Literal["consistent", "inconsistent", "insufficient_data"]
CaseType = Literal[
    "wrong_transfer",
    "payment_failed",
    "refund_request",
    "duplicate_payment",
    "merchant_settlement_delay",
    "agent_cash_in_issue",
    "phishing_or_social_engineering",
    "other",
]
Severity = Literal["low", "medium", "high", "critical"]
Department = Literal[
    "customer_support",
    "dispute_resolution",
    "payments_ops",
    "merchant_operations",
    "agent_operations",
    "fraud_risk",
]

# Plain tuples for runtime membership checks / validation in the reasoning layer.
CASE_TYPES = (
    "wrong_transfer",
    "payment_failed",
    "refund_request",
    "duplicate_payment",
    "merchant_settlement_delay",
    "agent_cash_in_issue",
    "phishing_or_social_engineering",
    "other",
)
DEPARTMENTS = (
    "customer_support",
    "dispute_resolution",
    "payments_ops",
    "merchant_operations",
    "agent_operations",
    "fraud_risk",
)
EVIDENCE_VERDICTS = ("consistent", "inconsistent", "insufficient_data")
SEVERITIES = ("low", "medium", "high", "critical")


# ---------------------------------------------------------------------------
# Request models (problem.md §5)
# ---------------------------------------------------------------------------


class TransactionEntry(BaseModel):
    """One entry in the customer's recent transaction history (§5.2).

    Optional enum-typed fields are intentionally typed as plain ``str`` rather
    than ``Literal`` so that an unexpected value in a hidden test degrades
    gracefully (we still reason over it) instead of producing a 422.
    """

    model_config = ConfigDict(extra="ignore")

    transaction_id: str
    timestamp: Optional[str] = None
    type: Optional[str] = None
    amount: Optional[float] = None
    counterparty: Optional[str] = None
    status: Optional[str] = None


class AnalyzeTicketRequest(BaseModel):
    """Request body for ``POST /analyze-ticket`` (§5).

    Only ``ticket_id`` and ``complaint`` are required. Unknown keys are ignored
    (``extra="ignore"``) so the harness can add simulated context without
    breaking us. Optional enum fields are plain strings for the same tolerance
    reason as ``TransactionEntry``.
    """

    model_config = ConfigDict(extra="ignore")

    ticket_id: str = Field(..., min_length=1)
    complaint: str
    language: Optional[str] = None
    channel: Optional[str] = None
    user_type: Optional[str] = None
    campaign_context: Optional[str] = None
    transaction_history: list[TransactionEntry] = Field(default_factory=list)
    metadata: Optional[dict] = None


# ---------------------------------------------------------------------------
# Response model (problem.md §6)
# ---------------------------------------------------------------------------


class AnalyzeTicketResponse(BaseModel):
    """Structured response for ``POST /analyze-ticket`` (§6).

    All 10 required fields plus the 2 optional fields. The four decision enums
    are ``Literal`` so an out-of-vocabulary value can never be serialized — the
    reasoning engine is responsible for only ever producing legal members.
    """

    ticket_id: str
    relevant_transaction_id: Optional[str] = None
    evidence_verdict: EvidenceVerdict
    case_type: CaseType
    severity: Severity
    department: Department
    agent_summary: str
    recommended_next_action: str
    customer_reply: str
    human_review_required: bool
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reason_codes: Optional[list[str]] = None
