"""Performance & reliability tests (problem.md §4.1, §9).

The service must never crash on bad input, must answer well within 30s, and must
never leak internals in an error body.
"""

import time

import pytest

GARBAGE_PAYLOADS = [
    {},                                   # empty object
    {"ticket_id": 12345},                 # wrong type, missing complaint
    {"complaint": "no ticket id here"},   # missing ticket_id
    {"ticket_id": "T", "complaint": None},  # null complaint
    {"ticket_id": "T", "complaint": "ok", "transaction_history": "not-a-list"},
    {"ticket_id": "T", "complaint": "ok", "transaction_history": [{"transaction_id": 1}]},
]


@pytest.mark.parametrize("payload", GARBAGE_PAYLOADS)
def test_garbage_input_never_5xx(client, payload):
    resp = client.post("/analyze-ticket", json=payload)
    # 400/422 are fine; the process must stay up and not 500 on malformed input.
    assert resp.status_code in (200, 400, 422), payload
    # Whatever the code, the body is JSON and never leaks a stack trace.
    body = resp.text.lower()
    assert "traceback" not in body
    assert "file \"" not in body


def test_oversized_complaint_handled(client):
    body = {"ticket_id": "TKT-BIG", "complaint": "x" * 200_000}
    resp = client.post("/analyze-ticket", json=body)
    assert resp.status_code in (200, 400, 422)


def test_health_is_fast(client):
    start = time.perf_counter()
    for _ in range(50):
        assert client.get("/health").status_code == 200
    assert (time.perf_counter() - start) < 5.0


def test_analyze_latency_under_budget(client, sample_cases):
    # Deterministic path: each request should be far under the 30s harness limit.
    for case in sample_cases:
        start = time.perf_counter()
        resp = client.post("/analyze-ticket", json=case["input"])
        elapsed = time.perf_counter() - start
        assert resp.status_code == 200
        assert elapsed < 5.0, f"{case['id']} took {elapsed:.2f}s"


def test_error_body_has_no_secrets(client):
    resp = client.post("/analyze-ticket", json={"ticket_id": "T"})
    assert resp.status_code == 400
    assert "openrouter" not in resp.text.lower()
    assert "api_key" not in resp.text.lower()
