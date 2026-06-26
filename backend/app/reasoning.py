"""Deterministic evidence-reasoning engine for the QueueStorm Investigator.

This is the "investigator, not classifier" core (problem.md §3). It reads the
complaint AND the supplied transaction history, decides which transaction the
complaint refers to, judges whether the data supports the complaint, classifies
and routes the case, and drafts safe agent/customer text.

Design choice (see plan.md Risks #3): the structured decisions —
``relevant_transaction_id``, ``evidence_verdict``, ``case_type``, ``department``,
``severity``, ``human_review_required`` — are produced by deterministic rules,
not a free-form LLM. That guarantees enum-exact output, sub-second latency, and
reproducible safety, none of which an LLM can guarantee. An LLM is *not* required
to score well (problem.md §12), and no API credits are provided. The prose fields
are produced by safe templates and may optionally be polished by an LLM behind a
schema-validating fallback (see ``llm.py``); the deterministic result is always a
complete, valid response on its own.

Calibrated against the 10 public sample cases in SUST_Preli_Sample_Cases.json.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import AnalyzeTicketRequest, AnalyzeTicketResponse, TransactionEntry

# ---------------------------------------------------------------------------
# Text normalisation helpers (English + Bangla)
# ---------------------------------------------------------------------------

_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def _normalize(text: str) -> str:
    """Lower-case and translate Bangla digits to ASCII for keyword/number scans."""
    return text.translate(_BANGLA_DIGITS).lower()


def _is_bangla(req: AnalyzeTicketRequest) -> bool:
    """Reply in Bangla when the request says so, or when the complaint is Bangla."""
    if (req.language or "").lower() in {"bn", "mixed"}:
        return True
    # Any character in the Bengali Unicode block.
    return any("ঀ" <= ch <= "৿" for ch in req.complaint)


def _extract_numbers(text: str) -> set[float]:
    """Pull plausible money amounts out of free text.

    We strip thousands separators, then read integer/decimal runs. Long digit
    runs (>= 7 digits, e.g. phone numbers like 01712345678) are excluded so a
    counterparty number is never mistaken for an amount. The caller intersects
    these against actual transaction amounts, which filters noise further.
    """
    cleaned = _normalize(text).replace(",", "")
    numbers: set[float] = set()
    for match in re.findall(r"\d+(?:\.\d+)?", cleaned):
        digits = match.split(".")[0]
        if len(digits) >= 7:  # phone numbers, long ids — not amounts
            continue
        try:
            numbers.add(float(match))
        except ValueError:
            continue
    return numbers


# ---------------------------------------------------------------------------
# Keyword vocabularies for case-type classification (English + Bangla)
# ---------------------------------------------------------------------------

_KW = {
    "phishing": [
        "otp", "pin", "password", "cvv", "card number", "scam", "phishing", "fraud",
        "suspicious", "will be blocked", "account will be blocked", "asked for my",
        "ওটিপি", "পিন", "পাসওয়ার্ড", "প্রতারণা", "ভুয়া", "সন্দেহজনক",
    ],
    "duplicate": [
        "twice", "two times", "double", "duplicate", "deducted twice", "charged twice",
        "দুইবার", "দুবার", "ডাবল",
    ],
    "agent_cash_in": [
        "cash in", "cash-in", "cashin", "cash in agent", "agent", "deposit through",
        "এজেন্ট", "ক্যাশ ইন", "ক্যাশইন",
    ],
    "settlement": ["settlement", "settle", "settled", "সেটেলমেন্ট"],
    "failed": [
        "failed", "transaction failed", "payment failed", "showed failed",
        "ব্যর্থ", "ফেইল",
    ],
    "wrong_transfer": [
        "wrong number", "wrong person", "wrong recipient", "wrong account",
        "wrong transfer", "sent to wrong", "didn't get", "did not get",
        "didn't receive", "did not receive", "hasn't received", "haven't received",
        "not received", "never received", "never got", "never arrived", "didn't arrive",
        "did not arrive", "ভুল নম্বর", "ভুল মানুষ", "পায়নি", "আসেনি", "পাইনি",
    ],
    "refund": [
        "refund", "changed my mind", "change my mind", "don't want", "do not want",
        "return my money", "money back", "ফেরত",
    ],
}


def _has(text: str, keywords: list[str]) -> bool:
    return any(kw in text for kw in keywords)


# ---------------------------------------------------------------------------
# Routing tables (problem.md §7.2). Deterministic so routing is always
# enum-exact. ``refund_request`` is resolved separately (it splits on whether
# the case is contested).
# ---------------------------------------------------------------------------

_DEPARTMENT_BY_CASE = {
    "wrong_transfer": "dispute_resolution",
    "payment_failed": "payments_ops",
    "duplicate_payment": "payments_ops",
    "merchant_settlement_delay": "merchant_operations",
    "agent_cash_in_issue": "agent_operations",
    "phishing_or_social_engineering": "fraud_risk",
    "other": "customer_support",
}

_BASE_SEVERITY = {
    "phishing_or_social_engineering": "critical",
    "wrong_transfer": "high",
    "payment_failed": "high",
    "duplicate_payment": "high",
    "agent_cash_in_issue": "high",
    "merchant_settlement_delay": "medium",
    "refund_request": "low",
    "other": "low",
}


# ---------------------------------------------------------------------------
# Reasoning result bundle
# ---------------------------------------------------------------------------


@dataclass
class _Decision:
    relevant_transaction_id: str | None
    evidence_verdict: str
    case_type: str
    severity: str
    department: str
    human_review_required: bool
    confidence: float
    reason_codes: list[str]
    matched_amount: float | None


# ---------------------------------------------------------------------------
# Step 1 — classify the case type
# ---------------------------------------------------------------------------


def _classify(text: str, req: AnalyzeTicketRequest) -> str:
    """First-match-wins precedence; safety-critical types are checked first."""
    if _has(text, _KW["phishing"]):
        return "phishing_or_social_engineering"
    if _has(text, _KW["duplicate"]):
        return "duplicate_payment"
    if _has(text, _KW["agent_cash_in"]):
        return "agent_cash_in_issue"
    if _has(text, _KW["settlement"]) or (req.user_type == "merchant" and "settle" in text):
        return "merchant_settlement_delay"
    if _has(text, _KW["failed"]):
        return "payment_failed"
    if _has(text, _KW["wrong_transfer"]):
        return "wrong_transfer"
    if _has(text, _KW["refund"]):
        return "refund_request"
    return "other"


# ---------------------------------------------------------------------------
# Step 2 — find the relevant transaction in the supplied history
# ---------------------------------------------------------------------------


def _find_relevant(
    case_type: str,
    amounts: set[float],
    txns: list[TransactionEntry],
) -> tuple[str | None, float | None, str]:
    """Return (transaction_id | None, matched_amount | None, match_reason).

    The match reason drives the evidence verdict downstream:
      - "single"      : exactly one transaction matched the claimed amount
      - "duplicate"   : two+ same-amount, same-counterparty (a duplicate group)
      - "ambiguous"   : multiple candidates across different counterparties
      - "none"        : nothing in history matches (or nothing to match)
    """
    if not txns:
        return None, None, "none"

    # Candidate transactions whose amount the customer actually named.
    candidates = [t for t in txns if t.amount is not None and t.amount in amounts]

    if not candidates:
        return None, None, "none"

    if len(candidates) == 1:
        return candidates[0].transaction_id, candidates[0].amount, "single"

    # Multiple candidates of the named amount.
    counterparties = {c.counterparty for c in candidates}
    if len(counterparties) == 1:
        # Same recipient repeated → a duplicate group. The relevant transaction
        # is the most recent one (the suspected duplicate, per SAMPLE-10).
        latest = max(candidates, key=lambda t: t.timestamp or "")
        reason = "duplicate" if case_type == "duplicate_payment" else "single"
        return latest.transaction_id, latest.amount, reason

    # Different recipients → we cannot tell which one the complaint means.
    return None, None, "ambiguous"


def _established_recipient(relevant_id: str | None, txns: list[TransactionEntry]) -> bool:
    """True when the matched transaction's counterparty appears more than once.

    A wrong-transfer claim against a recipient the customer has paid repeatedly
    is evidence-inconsistent (SAMPLE-02): the data suggests an established payee.
    """
    if relevant_id is None:
        return False
    matched = next((t for t in txns if t.transaction_id == relevant_id), None)
    if matched is None or matched.counterparty is None:
        return False
    same = [t for t in txns if t.counterparty == matched.counterparty]
    return len(same) >= 2


# ---------------------------------------------------------------------------
# Step 3 — assemble the full decision
# ---------------------------------------------------------------------------


def _decide(req: AnalyzeTicketRequest) -> _Decision:
    text = _normalize(req.complaint)
    txns = req.transaction_history or []
    case_type = _classify(text, req)

    # Phishing/social-engineering is a report about an interaction, not a ledger
    # entry — there is no transaction to verify, so evidence is insufficient and
    # the case is escalated to fraud at critical severity.
    if case_type == "phishing_or_social_engineering":
        return _Decision(
            relevant_transaction_id=None,
            evidence_verdict="insufficient_data",
            case_type=case_type,
            severity="critical",
            department="fraud_risk",
            human_review_required=True,
            confidence=0.95,
            reason_codes=["phishing", "credential_protection", "critical_escalation"],
            matched_amount=None,
        )

    amounts = _extract_numbers(req.complaint)
    relevant_id, matched_amount, match_reason = _find_relevant(case_type, amounts, txns)

    # ----- evidence verdict -------------------------------------------------
    if relevant_id is None:
        evidence_verdict = "insufficient_data"
    elif case_type == "wrong_transfer" and _established_recipient(relevant_id, txns):
        evidence_verdict = "inconsistent"
    else:
        evidence_verdict = "consistent"

    # ----- severity ---------------------------------------------------------
    severity = _BASE_SEVERITY.get(case_type, "low")
    # A wrong-transfer claim that the data does not cleanly support is a softer
    # signal than a confirmed one — drop it to medium (SAMPLE-02, SAMPLE-08).
    if case_type == "wrong_transfer" and evidence_verdict != "consistent":
        severity = "medium"

    # ----- department -------------------------------------------------------
    if case_type == "refund_request":
        # Contested refunds (evidence contradicts the customer) go to disputes;
        # ordinary "change of mind" refunds stay with customer support (§7.2).
        department = "dispute_resolution" if evidence_verdict == "inconsistent" else "customer_support"
    else:
        department = _DEPARTMENT_BY_CASE.get(case_type, "customer_support")

    # ----- human review -----------------------------------------------------
    # When we cannot even identify the transaction we ask the customer to
    # clarify rather than escalating (SAMPLE-06, SAMPLE-08 → false). Otherwise
    # disputes, duplicates, agent cash-in and any evidence contradiction escalate.
    if relevant_id is None:
        human_review_required = False
    else:
        human_review_required = (
            case_type in {"wrong_transfer", "duplicate_payment", "agent_cash_in_issue"}
            or evidence_verdict == "inconsistent"
        )

    # ----- confidence (optional, heuristic) ---------------------------------
    if evidence_verdict == "consistent":
        confidence = 0.9
    elif evidence_verdict == "inconsistent":
        confidence = 0.75
    elif match_reason == "ambiguous":
        confidence = 0.65
    else:
        confidence = 0.6

    # ----- reason codes (optional) ------------------------------------------
    reason_codes = [case_type]
    if relevant_id is not None:
        reason_codes.append("transaction_match")
    if match_reason == "ambiguous":
        reason_codes.append("ambiguous_match")
    if relevant_id is None and match_reason != "ambiguous":
        reason_codes.append("needs_clarification")
    if evidence_verdict == "inconsistent":
        reason_codes.append("evidence_inconsistent")

    return _Decision(
        relevant_transaction_id=relevant_id,
        evidence_verdict=evidence_verdict,
        case_type=case_type,
        severity=severity,
        department=department,
        human_review_required=human_review_required,
        confidence=confidence,
        reason_codes=reason_codes,
        matched_amount=matched_amount,
    )


# ---------------------------------------------------------------------------
# Step 4 — draft safe prose (agent_summary, recommended_next_action,
# customer_reply). Templates are safe by construction; safety.enforce_reply is
# applied afterwards as defense-in-depth.
# ---------------------------------------------------------------------------

_SAFETY_LINE_EN = "Please do not share your PIN or OTP with anyone."
_SAFETY_LINE_BN = "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"


def _tid(decision: _Decision) -> str:
    return decision.relevant_transaction_id or "the relevant transaction"


def _prose_en(decision: _Decision) -> tuple[str, str, str]:
    ct = decision.case_type
    tid = _tid(decision)
    if ct == "phishing_or_social_engineering":
        return (
            "Customer reports a suspected phishing or social-engineering attempt "
            "(unsolicited request for credentials). No transaction to verify.",
            "Escalate to the fraud_risk team. Confirm to the customer that the company "
            "never asks for PIN or OTP. Log any reported number for fraud analysis.",
            "Thank you for reaching out before sharing any information. We never ask for "
            "your PIN, OTP, or password under any circumstances. Please do not share these "
            "with anyone, even if they claim to be from us. Our fraud team has been notified "
            "of this incident.",
        )
    if ct == "wrong_transfer" and decision.relevant_transaction_id is None:
        return (
            "Customer reports a transfer that the recipient did not receive, but multiple "
            "transactions plausibly match and the correct one cannot be identified from the "
            "provided history.",
            "Reply to the customer asking for the recipient's number and exact amount to "
            "identify the correct transaction. Do not initiate a dispute until confirmed.",
            f"Thank you for reaching out. We see more than one transaction that could match "
            f"your description. Could you share the recipient's number and the exact amount so "
            f"we can identify the right transaction? {_SAFETY_LINE_EN}",
        )
    if ct == "wrong_transfer":
        verdict_note = (
            " Transaction history shows prior transfers to the same recipient, which may "
            "contradict the wrong-transfer claim."
            if decision.evidence_verdict == "inconsistent"
            else ""
        )
        return (
            f"Customer reports {tid} was sent to the wrong recipient.{verdict_note}",
            f"Verify {tid} with the customer and proceed with the wrong-transfer dispute "
            f"workflow per policy." if decision.evidence_verdict == "consistent"
            else f"Flag for human review. Verify with the customer whether {tid} was genuinely "
            f"a wrong transfer given the established pattern with this recipient.",
            f"We have noted your concern about transaction {tid}. Our dispute team will review "
            f"the case and contact you through official support channels. {_SAFETY_LINE_EN}",
        )
    if ct == "payment_failed":
        return (
            f"Customer attempted a payment ({tid}) that failed but reports the balance was "
            f"deducted. Requires payments operations investigation.",
            f"Investigate the {tid} ledger status. If the balance was deducted on a failed "
            f"payment, initiate the reversal flow within standard SLA.",
            f"We have noted that transaction {tid} may have caused an unexpected balance "
            f"deduction. Our payments team will review the case and any eligible amount will be "
            f"returned through official channels. {_SAFETY_LINE_EN}",
        )
    if ct == "duplicate_payment":
        return (
            f"Customer reports a duplicate payment. {tid} appears to be a repeated charge to "
            f"the same biller within a short window.",
            f"Verify the duplicate with payments_ops. If the biller confirms a single payment "
            f"was received, initiate reversal of {tid}.",
            f"We have noted the possible duplicate payment for transaction {tid}. Our payments "
            f"team will verify with the biller and any eligible amount will be returned through "
            f"official channels. {_SAFETY_LINE_EN}",
        )
    if ct == "agent_cash_in_issue":
        return (
            f"Customer reports an agent cash-in ({tid}) not reflected in their balance.",
            f"Investigate {tid} with agent operations. Confirm the settlement state and resolve "
            f"within the standard cash-in SLA.",
            f"We have noted your concern about transaction {tid}. Our agent operations team will "
            f"review it and update you through official support channels. {_SAFETY_LINE_EN}",
        )
    if ct == "merchant_settlement_delay":
        return (
            f"Merchant reports settlement {tid} is delayed beyond the expected window.",
            f"Route to merchant_operations to verify the settlement batch status. If delayed, "
            f"communicate a revised ETA to the merchant.",
            f"We have noted your concern about settlement {tid}. Our merchant operations team "
            f"will check the batch status and update you on the expected settlement time through "
            f"official channels.",
        )
    if ct == "refund_request":
        return (
            f"Customer requests a refund for {tid}. Not a service failure.",
            "Inform the customer that refund eligibility depends on the merchant's own policy "
            "and provide guidance on contacting the merchant directly.",
            f"Thank you for reaching out. Refunds for completed merchant payments depend on the "
            f"merchant's own policy. We recommend contacting the merchant directly, and we can "
            f"guide you if you need help. {_SAFETY_LINE_EN}",
        )
    # other / vague
    return (
        "Customer reports a vague concern without specifying a transaction, amount, or issue. "
        "Insufficient detail to identify a relevant transaction.",
        "Reply to the customer asking for specific details: which transaction, what amount, "
        "what went wrong, and the approximate time.",
        f"Thank you for reaching out. To help you faster, please share the transaction ID, the "
        f"amount involved, and a short description of what went wrong. {_SAFETY_LINE_EN}",
    )


def _customer_reply_bn(decision: _Decision) -> str:
    ct = decision.case_type
    tid = _tid(decision)
    if ct == "phishing_or_social_engineering":
        return (
            "কোনো তথ্য শেয়ার করার আগে যোগাযোগ করার জন্য ধন্যবাদ। আমরা কখনোই আপনার পিন, ওটিপি বা "
            "পাসওয়ার্ড চাই না। কেউ নিজেকে আমাদের প্রতিনিধি দাবি করলেও এগুলো শেয়ার করবেন না। "
            "আমাদের ফ্রড টিমকে বিষয়টি জানানো হয়েছে।"
        )
    if ct == "refund_request":
        return (
            "যোগাযোগ করার জন্য ধন্যবাদ। সম্পন্ন হওয়া মার্চেন্ট পেমেন্টের রিফান্ড মার্চেন্টের নিজস্ব "
            f"নীতির উপর নির্ভর করে। সরাসরি মার্চেন্টের সাথে যোগাযোগ করার পরামর্শ দিচ্ছি। {_SAFETY_LINE_BN}"
        )
    if ct == "other" or decision.relevant_transaction_id is None:
        return (
            "যোগাযোগ করার জন্য ধন্যবাদ। দ্রুত সহায়তার জন্য অনুগ্রহ করে লেনদেন আইডি, পরিমাণ এবং "
            f"সমস্যার সংক্ষিপ্ত বিবরণ জানান। {_SAFETY_LINE_BN}"
        )
    # Generic transaction-acknowledgement reply (safe for all remaining types).
    dept_bn = {
        "dispute_resolution": "ডিসপিউট",
        "payments_ops": "পেমেন্টস",
        "agent_operations": "এজেন্ট অপারেশন্স",
        "merchant_operations": "মার্চেন্ট অপারেশন্স",
        "fraud_risk": "ফ্রড",
        "customer_support": "কাস্টমার সাপোর্ট",
    }.get(decision.department, "সংশ্লিষ্ট")
    return (
        f"আপনার লেনদেন {tid} এর বিষয়ে আমরা অবগত হয়েছি। আমাদের {dept_bn} দল এটি দ্রুত যাচাই করবে এবং "
        f"অফিসিয়াল চ্যানেলে আপনাকে জানাবে। {_SAFETY_LINE_BN}"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def analyze(req: AnalyzeTicketRequest) -> AnalyzeTicketResponse:
    """Run the full deterministic investigation and return a valid response."""
    from . import safety  # local import avoids a circular import at module load

    decision = _decide(req)
    agent_summary, recommended_next_action, customer_reply_en = _prose_en(decision)

    if _is_bangla(req):
        customer_reply = _customer_reply_bn(decision)
    else:
        customer_reply = customer_reply_en

    # Defense-in-depth: scrub the generated text against every safety rule even
    # though the templates are already safe. Echoed complaint text never reaches
    # these fields, so injection in the complaint cannot alter them.
    customer_reply = safety.enforce_reply(customer_reply, bangla=_is_bangla(req))
    recommended_next_action = safety.enforce_action(recommended_next_action)

    return AnalyzeTicketResponse(
        ticket_id=req.ticket_id,
        relevant_transaction_id=decision.relevant_transaction_id,
        evidence_verdict=decision.evidence_verdict,
        case_type=decision.case_type,
        severity=decision.severity,
        department=decision.department,
        agent_summary=agent_summary,
        recommended_next_action=recommended_next_action,
        customer_reply=customer_reply,
        human_review_required=decision.human_review_required,
        confidence=round(decision.confidence, 2),
        reason_codes=decision.reason_codes,
    )


def safe_fallback(ticket_id: str, bangla: bool = False) -> AnalyzeTicketResponse:
    """A schema-valid, maximally-safe response used when reasoning cannot run.

    Used by the handler if anything unexpected happens (T-11): escalate, assume
    insufficient evidence, route to customer support, and reply safely. Never a 500.
    """
    reply = (
        "যোগাযোগ করার জন্য ধন্যবাদ। আপনার অনুরোধটি পর্যালোচনার জন্য আমাদের সাপোর্ট দলের কাছে "
        f"পাঠানো হয়েছে। {_SAFETY_LINE_BN}"
        if bangla
        else "Thank you for reaching out. Your request has been received and forwarded to our "
        f"support team for review. {_SAFETY_LINE_EN}"
    )
    return AnalyzeTicketResponse(
        ticket_id=ticket_id or "unknown",
        relevant_transaction_id=None,
        evidence_verdict="insufficient_data",
        case_type="other",
        severity="low",
        department="customer_support",
        agent_summary="The case could not be analysed automatically and was routed for manual review.",
        recommended_next_action="Review the ticket manually and follow up with the customer for details.",
        customer_reply=reply,
        human_review_required=True,
        confidence=None,
        reason_codes=["fallback", "manual_review"],
    )
