"""API contract & schema tests (problem.md §4, §6)."""

import pytest

REQUIRED_FIELDS = [
    "ticket_id",
    "relevant_transaction_id",
    "evidence_verdict",
    "case_type",
    "severity",
    "department",
    "agent_summary",
    "recommended_next_action",
    "customer_reply",
    "human_review_required",
]


def test_health_exact(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}  # exactly, no extra keys


def test_analyze_returns_all_required_fields(client, sample_cases):
    out = client.post("/analyze-ticket", json=sample_cases[0]["input"]).json()
    for field in REQUIRED_FIELDS:
        assert field in out, f"missing required field: {field}"


def test_ticket_id_echoed(client):
    body = {"ticket_id": "TKT-ECHO-123", "complaint": "I sent money to a wrong number."}
    out = client.post("/analyze-ticket", json=body).json()
    assert out["ticket_id"] == "TKT-ECHO-123"


def test_enum_values_are_legal(client, sample_cases, allowed_enums):
    for case in sample_cases:
        out = client.post("/analyze-ticket", json=case["input"]).json()
        assert out["evidence_verdict"] in allowed_enums["evidence_verdict"]
        assert out["case_type"] in allowed_enums["case_type"]
        assert out["severity"] in allowed_enums["severity"]
        assert out["department"] in allowed_enums["department"]


def test_missing_required_field_is_400(client):
    # No 'complaint' → malformed input → 400 (not FastAPI's default 422).
    resp = client.post("/analyze-ticket", json={"ticket_id": "TKT-1"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_invalid_json_is_400(client):
    resp = client.post(
        "/analyze-ticket",
        content=b"{not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_empty_complaint_is_422(client):
    resp = client.post("/analyze-ticket", json={"ticket_id": "TKT-1", "complaint": "   "})
    assert resp.status_code == 422


def test_minimal_request_succeeds(client):
    # Only the two required fields, no transaction_history.
    resp = client.post("/analyze-ticket", json={"ticket_id": "TKT-X", "complaint": "Help me."})
    assert resp.status_code == 200
    assert resp.json()["ticket_id"] == "TKT-X"


def test_unknown_keys_ignored(client):
    body = {
        "ticket_id": "TKT-U",
        "complaint": "I sent 5000 to a wrong number.",
        "surprise_field": {"nested": True},
        "metadata": {"anything": "goes"},
    }
    resp = client.post("/analyze-ticket", json=body)
    assert resp.status_code == 200
