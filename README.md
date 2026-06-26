# QueueStorm Investigator

A deterministic API service that triages digital-finance support tickets. Given a customer complaint and a short snippet of that customer's recent transaction history, it identifies the relevant transaction, evaluates whether the data supports the claim, routes the case to the correct team, and generates a safe customer reply — all in under 100 ms with no external dependencies.

---

## Live service

| | |
|---|---|
| Base URL | `https://chatbot-backend-production-7fe7.up.railway.app` |
| Health | `GET /health` → `{"status":"ok"}` |
| Analyze | `POST /analyze-ticket` |
| Docker image | `docker pull maruf52230/queuestorm-investigator:latest` |

```bash
curl https://chatbot-backend-production-7fe7.up.railway.app/health
# {"status":"ok"}
```

---

## API

### `POST /analyze-ticket`

**Request**

```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to the wrong number.",
  "language": "en",
  "transaction_history": [
    {
      "transaction_id": "TXN-9101",
      "timestamp": "2026-04-14T14:08:22Z",
      "type": "transfer",
      "amount": 5000,
      "counterparty": "+8801719876543",
      "status": "completed"
    }
  ]
}
```

`ticket_id` and `complaint` are required. `transaction_history`, `language`, `channel`,
`user_type`, `campaign_context`, and `metadata` are optional.

**Response**

```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports TXN-9101 was sent to the wrong recipient.",
  "recommended_next_action": "Verify TXN-9101 with the customer and proceed with the dispute workflow per policy.",
  "customer_reply": "We have noted your concern about transaction TXN-9101. Our dispute team will review the case and contact you through official support channels. Please do not share your PIN or OTP with anyone.",
  "human_review_required": true,
  "confidence": 0.9,
  "reason_codes": ["wrong_transfer", "transaction_match"]
}
```

**HTTP status codes**

| Code | Meaning |
|------|---------|
| 200 | Successful analysis |
| 400 | Malformed input — invalid JSON or missing required fields |
| 422 | Schema-valid but semantically empty complaint |
| 500 | Internal error — safe, non-sensitive message, no stack trace |

The service never crashes on bad input.

### `GET /health`

Returns `{"status":"ok"}` with no I/O. Used as a readiness probe.

---

## How it works

The reasoning is fully deterministic — no LLM, no external API call on the analysis path.

**1. Classification**

The complaint is scanned for keywords (English, Bangla, and Banglish) to determine one of eight case types: `wrong_transfer`, `payment_failed`, `refund_request`, `duplicate_payment`, `merchant_settlement_delay`, `agent_cash_in_issue`, `phishing_or_social_engineering`, or `other`. Safety-critical types are evaluated first.

**2. Transaction matching**

The customer's stated amount is extracted from the complaint and intersected against the supplied transaction history to identify `relevant_transaction_id`. Magnitude shorthand (`5k`, `5 thousand`, `৫ লাখ`) and Bangla numerals are normalised before matching. Long digit sequences (phone numbers) are excluded to avoid false matches.

**3. Evidence verdict**

The service determines whether the transaction data supports or contradicts the complaint:

- `consistent` — the ledger entry supports the claim.
- `inconsistent` — the data contradicts it (e.g. a "payment failed" complaint against a `completed` transaction, or a "wrong transfer" to a recipient the customer has paid repeatedly).
- `insufficient_data` — no matching transaction found, or the match is ambiguous. The service does not guess.

**4. Routing**

Department, severity, and `human_review_required` are assigned by deterministic rules. Disputes, fraud cases, and duplicates are escalated; ambiguous cases without a matched transaction prompt clarification rather than escalation.

**5. Response generation**

`agent_summary`, `recommended_next_action`, and `customer_reply` are produced from safe templates and then independently validated by the safety layer before being returned.

---

## Safety guardrails

Every customer-facing field passes through `backend/app/safety.py` as defense-in-depth on top of already-safe templates.

| Rule | Enforcement |
|------|-------------|
| Never request PIN, OTP, password, or card number | Outgoing replies are scanned for solicitation patterns. Safe warning phrases ("do not share your PIN") are explicitly allowed. Complaint text is never echoed into output fields. |
| Never confirm an unauthorized refund, reversal, or account unblock | Guaranteeing language is replaced with "any eligible amount will be returned through official channels". Applied to both `customer_reply` and `recommended_next_action`. |
| Never redirect to a suspicious third party | Replies reference only official support channels. |
| Prompt injection resistance | The engine never copies complaint text into output fields, so instructions embedded in a complaint have no surface to act on. |

---

## Tech stack

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI |
| Language | Python 3.12 |
| Schema validation | Pydantic v2 |
| Server | Uvicorn (2 workers) |
| Testing | Pytest — 102 tests |
| Deployment | Railway |
| Container | Docker (`python:3.12-slim`, non-root user) |

No database. No GPU. No outbound network call on the analysis path. Zero inference cost.

---

## Running locally

### Option 1 — Pull from Docker Hub

```bash
docker pull maruf52230/queuestorm-investigator:latest
docker run --rm -p 8000:8000 maruf52230/queuestorm-investigator:latest
```

If port 8000 is in use, map a different host port:

```bash
docker run --rm -p 8090:8000 maruf52230/queuestorm-investigator:latest
```

### Option 2 — Build and run with Docker Compose

```bash
docker compose up --build           # foreground
docker compose up -d --build        # detached
docker compose down                 # stop and remove

HOST_PORT=8090 docker compose up    # if port 8000 is taken
```

Environment variables (all optional):

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Port the app binds inside the container |
| `HOST_PORT` | `8000` | Host port published by Docker Compose |
| `WEB_CONCURRENCY` | `2` | Number of Uvicorn worker processes |
| `CORS_ORIGINS` | `*` | Comma-separated origin allowlist, or `*` for all |

### Option 3 — Python directly

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Verify:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

102 tests covering API contract, evidence reasoning, amount parsing robustness, safety
guardrails, and response-time reliability.

---

## Known limitations

- Amounts must contain a digit. Digit forms, magnitude shorthand (`5k`, `৫ লাখ`), and Bangla
  numerals are handled; fully written amounts ("five thousand") fall back to
  `insufficient_data` rather than guess.
- Complaint types outside the supported taxonomy are mapped to `other` / `customer_support`
  with `insufficient_data`.
- Bangla customer replies use fixed templates rather than generative text.

---

## Repository layout

```
backend/
  app/
    main.py          # FastAPI app, endpoints, error handlers
    reasoning.py     # Deterministic evidence-reasoning engine
    safety.py        # Safety guardrails and output scanning
    schemas.py       # Pydantic request/response models
    config.py        # Settings (CORS, workers)
  requirements.txt
  Dockerfile
tests/               # 102 Pytest tests
docker-compose.yml
RUNBOOK.md           # Copy-paste deployment reference
sample_output.json   # Example outputs   for all sample cases
```
