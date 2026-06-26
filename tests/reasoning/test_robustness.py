"""Robustness tests for the reasoning engine beyond the 10 public samples.

Covers the two hidden-test hardening additions:
  * amount parsing with magnitude units ("5k", "5 thousand", "৫ লাখ", Bangla digits)
  * ledger-status-aware evidence verdicts (the §3 "investigator" twist)
"""

from app.reasoning import _extract_numbers, analyze
from app.schemas import AnalyzeTicketRequest, TransactionEntry


# ---------------------------------------------------------------------------
# Amount parsing
# ---------------------------------------------------------------------------


def test_bare_and_comma_amounts():
    nums = _extract_numbers("I sent 5,000 taka")
    assert 5000 in nums


def test_k_suffix():
    assert 5000 in _extract_numbers("sent 5k by mistake")
    assert 5000 in _extract_numbers("transferred 5K to wrong number")


def test_thousand_word():
    assert 5000 in _extract_numbers("paid 5 thousand taka")


def test_lakh_and_crore():
    assert 100_000 in _extract_numbers("lost 1 lakh")
    assert 200_000 in _extract_numbers("2 lac gone")
    assert 10_000_000 in _extract_numbers("1 crore settlement")


def test_bangla_digits_and_unit():
    # "৫ হাজার" -> 5 thousand -> 5000, "৫০০০" -> 5000
    assert 5000 in _extract_numbers("৫ হাজার টাকা পাঠিয়েছি")
    assert 5000 in _extract_numbers("৫০০০ টাকা")
    assert 500_000 in _extract_numbers("৫ লাখ")


def test_phone_number_not_treated_as_amount():
    # 11-digit phone must not be picked up as an amount.
    nums = _extract_numbers("I sent money to 01712345678")
    assert 1712345678 not in nums
    assert not any(n >= 1_000_000_0 for n in nums)


def test_k_amount_matches_transaction_end_to_end():
    """A complaint that writes the amount as "5k" still identifies the txn."""
    req = AnalyzeTicketRequest(
        ticket_id="TKT-K",
        complaint="I sent 5k to the wrong number this afternoon",
        transaction_history=[
            TransactionEntry(
                transaction_id="TXN-1",
                amount=5000,
                counterparty="+8801700000000",
                status="completed",
                timestamp="2026-04-14T14:00:00Z",
            )
        ],
    )
    out = analyze(req)
    assert out.relevant_transaction_id == "TXN-1"
    assert out.evidence_verdict == "consistent"
    assert out.case_type == "wrong_transfer"


# ---------------------------------------------------------------------------
# Ledger-status-aware verdicts
# ---------------------------------------------------------------------------


def _txn(tid, amount, status):
    return TransactionEntry(
        transaction_id=tid,
        amount=amount,
        counterparty="+8801711111111",
        status=status,
        timestamp="2026-04-14T14:00:00Z",
    )


def test_payment_failed_but_ledger_completed_is_inconsistent():
    req = AnalyzeTicketRequest(
        ticket_id="TKT-PF",
        complaint="My payment of 1200 failed but money was deducted",
        transaction_history=[_txn("TXN-PF", 1200, "completed")],
    )
    out = analyze(req)
    assert out.case_type == "payment_failed"
    assert out.relevant_transaction_id == "TXN-PF"
    assert out.evidence_verdict == "inconsistent"
    assert out.human_review_required is True
    assert "ledger_status_conflict" in (out.reason_codes or [])


def test_payment_failed_with_failed_status_is_consistent():
    req = AnalyzeTicketRequest(
        ticket_id="TKT-PF2",
        complaint="My payment of 1200 failed but money was deducted",
        transaction_history=[_txn("TXN-PF2", 1200, "failed")],
    )
    out = analyze(req)
    assert out.evidence_verdict == "consistent"


def test_wrong_transfer_with_failed_status_is_inconsistent():
    req = AnalyzeTicketRequest(
        ticket_id="TKT-WT",
        complaint="I sent 3000 to the wrong number",
        transaction_history=[_txn("TXN-WT", 3000, "failed")],
    )
    out = analyze(req)
    assert out.case_type == "wrong_transfer"
    assert out.evidence_verdict == "inconsistent"
