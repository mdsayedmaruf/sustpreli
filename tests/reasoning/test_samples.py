"""Evidence-reasoning verification against the 10 public sample cases.

The bar (per the sample pack's how_to_use) is *functional equivalence*: same
relevant_transaction_id, same evidence_verdict, same case_type, same department,
and comparable severity — not byte-for-byte text equality.
"""

import pytest

# Severity ordering for the "comparable severity" check (within one step).
_SEV_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _post(client, case):
    resp = client.post("/analyze-ticket", json=case["input"])
    assert resp.status_code == 200, f"{case['id']}: HTTP {resp.status_code}"
    return resp.json()


def test_all_samples_present(sample_cases):
    assert len(sample_cases) == 10


@pytest.mark.parametrize("idx", range(10))
def test_relevant_transaction_id(client, sample_cases, idx):
    case = sample_cases[idx]
    out = _post(client, case)
    assert out["relevant_transaction_id"] == case["expected_output"]["relevant_transaction_id"], (
        f"{case['id']}: relevant_transaction_id mismatch"
    )


@pytest.mark.parametrize("idx", range(10))
def test_evidence_verdict(client, sample_cases, idx):
    case = sample_cases[idx]
    out = _post(client, case)
    assert out["evidence_verdict"] == case["expected_output"]["evidence_verdict"], (
        f"{case['id']}: evidence_verdict mismatch"
    )


@pytest.mark.parametrize("idx", range(10))
def test_case_type(client, sample_cases, idx):
    case = sample_cases[idx]
    out = _post(client, case)
    assert out["case_type"] == case["expected_output"]["case_type"], (
        f"{case['id']}: case_type mismatch"
    )


@pytest.mark.parametrize("idx", range(10))
def test_department(client, sample_cases, idx):
    case = sample_cases[idx]
    out = _post(client, case)
    assert out["department"] == case["expected_output"]["department"], (
        f"{case['id']}: department mismatch"
    )


@pytest.mark.parametrize("idx", range(10))
def test_severity_comparable(client, sample_cases, idx):
    case = sample_cases[idx]
    out = _post(client, case)
    expected = case["expected_output"]["severity"]
    got = out["severity"]
    assert abs(_SEV_RANK[got] - _SEV_RANK[expected]) <= 1, (
        f"{case['id']}: severity {got} not comparable to {expected}"
    )


@pytest.mark.parametrize("idx", range(10))
def test_human_review_required(client, sample_cases, idx):
    case = sample_cases[idx]
    out = _post(client, case)
    assert out["human_review_required"] == case["expected_output"]["human_review_required"], (
        f"{case['id']}: human_review_required mismatch"
    )
