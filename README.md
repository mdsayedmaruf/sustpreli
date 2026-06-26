# QueueStorm Investigator — AI/API SupportOps Service

An evidence-grounded support copilot for the **bKash · SUST CSE Carnival 2026 — Codex
Community Hackathon** (AI/API SupportOps Challenge). It exposes a small FastAPI service
that reads one customer complaint plus that customer's recent transaction history,
decides **what actually happened**, routes the case to the right team, and drafts a
**safe** reply — returning spec-exact JSON within the 30-second budget.

> The solution is a complaint *investigator*, not a classifier. The complaint says one
> thing; the transaction data may say another. The service reasons from the supplied
> evidence and, when the evidence is genuinely unclear, says so (`insufficient_data`)
> instead of guessing.

---

## Endpoints (problem.md §4)

| Method | Path              | Purpose                                                        |
|--------|-------------------|----------------------------------------------------------------|
| `GET`  | `/health`         | Readiness probe. Returns exactly `{"status":"ok"}`, no I/O.    |
| `POST` | `/analyze-ticket` | Analyse one ticket; returns the structured response (§6).      |

HTTP codes: `200` success · `400` malformed input (invalid JSON / missing required
fields) · `422` schema-valid but semantically empty complaint · `500` internal error
(non-sensitive). The process never crashes on bad input.

### Example

```bash
curl -s http://localhost:8000/analyze-ticket -H "Content-Type: application/json" -d '{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to a wrong number around 2pm today.",
  "transaction_history": [
    {"transaction_id":"TXN-9101","timestamp":"2026-04-14T14:08:22Z","type":"transfer","amount":5000,"counterparty":"+8801719876543","status":"completed"}
  ]
}'
```

```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports TXN-9101 was sent to the wrong recipient.",
  "recommended_next_action": "Verify TXN-9101 with the customer and proceed with the wrong-transfer dispute workflow per policy.",
  "customer_reply": "We have noted your concern about transaction TXN-9101. Our dispute team will review the case and contact you through official support channels. Please do not share your PIN or OTP with anyone.",
  "human_review_required": true,
  "confidence": 0.9,
  "reason_codes": ["wrong_transfer", "transaction_match"]
}
```

A full set of outputs for all 10 public sample cases is checked in at
[`sample_output.json`](./sample_output.json).

---

## Tech stack

- **Python 3.12+ / FastAPI / Uvicorn** — async HTTP service.
- **Pydantic v2** — request/response schema with the exact spec enums as `Literal`
  types, so an illegal enum value can never be serialised.
- **Pytest** — 92 tests: contract, the 10 sample cases, safety, and reliability.
- No database, no GPU, and **no required outbound network call** on the analysis path.

## AI approach — how it reasons

The reasoning is a **deterministic rule engine** (`backend/app/reasoning.py`), not a
free-form LLM, calibrated against the 10 public sample cases:

1. **Classify** the case type from complaint keywords (English + Bangla), with
   safety-critical types (phishing) checked first.
2. **Match evidence** — the customer's named amount is intersected against the supplied
   `transaction_history` to pick `relevant_transaction_id`. Amounts written with a
   magnitude unit (`5k`, `5 thousand`, `৫ লাখ`) and Bangla numerals are normalised before
   matching. Long digit runs (phone numbers) are excluded so a counterparty number is
   never mistaken for an amount.
3. **Judge the evidence** — `consistent` when the data supports the complaint;
   `inconsistent` when it contradicts it (e.g. a "wrong transfer" to a recipient the
   customer has paid repeatedly, or a claim whose ledger **status** disproves it — a
   "payment failed" against a `completed` transaction, a "wrong transfer" against money
   that never left via a `failed`/`reversed` entry); `insufficient_data` when no
   transaction matches, the match is ambiguous, or the complaint is vague. **When unsure,
   it does not guess.**
4. **Route** deterministically to the department per §7.2, assign severity, and decide
   `human_review_required` (escalate disputes/fraud/duplicates; ask for clarification
   rather than escalate when the transaction can't even be identified).
5. **Draft prose** from safe templates, multilingual (Bangla reply for Bangla input).

Why deterministic? It guarantees **enum-exact** output, **sub-millisecond** latency
(no timeout risk), and **reproducible safety** — none of which an LLM guarantees. The
problem statement is explicit that an LLM is not required to score well (§12), and no
LLM credits are provided.

## Safety logic (problem.md §8)

Every customer-facing string passes through `backend/app/safety.py`, which enforces the
four auto-checked rules as defense-in-depth on top of already-safe templates:

| Rule | Penalty | How it's enforced |
|------|---------|-------------------|
| Never request PIN / OTP / password / full card | −15 | Reply scanned for solicitation patterns; warning phrasings ("do not share your PIN") are explicitly allowed. Credentials in the complaint are never echoed back. |
| Never confirm an unauthorized refund / reversal / unblock | −10 | Guaranteeing language ("we will refund you") is replaced with "any eligible amount will be returned through official channels". Applies to `customer_reply` **and** `recommended_next_action`. |
| Never direct to a suspicious third party | −10 | Replies only ever point to official support channels. |
| Ignore prompt injection in the complaint | rule | The engine never copies complaint text into output fields, so embedded "ignore your rules" instructions have no surface to act on. |

These rules are covered by `tests/safety/` with explicit negative tests.

## Model & cost reasoning (MODELS)

**No external LLM is used on the scoring path.** The service runs a self-contained,
deterministic rule engine:

- **Cost:** $0 inference cost — no API credits required, no per-request token spend.
- **Latency:** every sample case responds in well under a second (see
  `tests/reliability/test_analyze_latency_under_budget`), comfortably inside the 30s
  budget with no timeout exposure.
- **No outbound calls:** the analysis path makes no network request at all, so there is
  no API key to manage and no external dependency that can fail or add latency.

## Assumptions

- "Comparable severity" is the bar (per the sample pack), not exact-match severity;
  thresholds are calibrated to the 10 sample rationales.
- A refund complaint is routed to `dispute_resolution` only when the evidence
  contradicts the customer (contested); ordinary change-of-mind refunds go to
  `customer_support`.
- The relevant transaction is the one whose amount the complaint names; for a duplicate
  group (same amount + counterparty), the most recent transaction is the suspected duplicate.

## Known limitations

- Amount matching needs a number; digit forms, magnitude units (`5k`, `৫ লাখ`), and
  Bangla numerals are handled, but a fully spelled-out amount with no digit ("five
  thousand") falls back to `insufficient_data` rather than guess — a deliberately safe
  failure mode.
- The rule engine is tuned to the public taxonomy; genuinely novel hidden scenarios map
  to `other` / `customer_support` with `insufficient_data`, which is safe but conservative.
- Bangla prose uses fixed templates rather than generative phrasing.

---

## Run it

See [`RUNBOOK.md`](./RUNBOOK.md) for copy-paste local, Docker, and deploy steps.

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
# GET http://localhost:8000/health  →  {"status":"ok"}
```

Run the tests:

```bash
pip install -r requirements-dev.txt
pytest            # 92 tests: contract, 10 sample cases, safety, reliability
```
