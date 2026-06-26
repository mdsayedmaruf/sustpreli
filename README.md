# QueueStorm Investigator — Support Ticket Analysis API

A small, fast service that helps digital-finance support teams triage complaints. It reads
one customer complaint plus that customer's recent transaction history, decides **what
actually happened**, routes the case to the right team, and drafts a **safe** reply —
returning structured JSON in milliseconds.

> It's a complaint *investigator*, not a classifier. The complaint says one thing; the
> transaction data may say another. The service reasons from the supplied evidence and,
> when the evidence is genuinely unclear, says so (`insufficient_data`) instead of guessing.

---

## 🚀 Live service

**Base URL:** <https://chatbot-backend-production-7fe7.up.railway.app>

| | |
|---|---|
| **Health**  | <https://chatbot-backend-production-7fe7.up.railway.app/health> → `{"status":"ok"}` |
| **Analyze** | `POST` https://chatbot-backend-production-7fe7.up.railway.app/analyze-ticket |
| **Docker**  | `docker pull maruf52230/queuestorm-investigator:latest` |

Try it in one line:

```bash
curl -s https://chatbot-backend-production-7fe7.up.railway.app/analyze-ticket \
  -H "Content-Type: application/json" \
  -d '{"ticket_id":"TKT-001","complaint":"I sent 5k to a wrong number","transaction_history":[{"transaction_id":"TXN-9101","amount":5000,"counterparty":"+8801719876543","status":"completed"}]}'
```

---

## Endpoints

| Method | Path              | Purpose                                                        |
|--------|-------------------|----------------------------------------------------------------|
| `GET`  | `/health`         | Readiness probe. Returns exactly `{"status":"ok"}`, no I/O.    |
| `POST` | `/analyze-ticket` | Analyse one ticket; returns the structured response.           |

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

A set of example outputs is checked in at [`sample_output.json`](./sample_output.json).

---

## Tech stack

- **Python 3.12+ / FastAPI / Uvicorn** — async HTTP service.
- **Pydantic v2** — request/response schema with the output enums as `Literal` types, so an
  illegal enum value can never be serialised.
- **Pytest** — 102 tests: contract, reasoning, robustness, safety, and reliability.
- No database, no GPU, and **no required outbound network call** on the analysis path.

## How it reasons

The reasoning is a **deterministic rule engine** (`backend/app/reasoning.py`), not a
free-form LLM:

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
4. **Route** deterministically to the right department, assign severity, and decide
   `human_review_required` (escalate disputes/fraud/duplicates; ask for clarification
   rather than escalate when the transaction can't even be identified).
5. **Draft prose** from safe templates, multilingual (Bangla reply for Bangla input).

Why deterministic? It guarantees **enum-exact** output, **sub-millisecond** latency, and
**reproducible safety** — none of which a free-form LLM guarantees — at zero inference cost.

## Safety logic

Every customer-facing string passes through `backend/app/safety.py`, which enforces these
rules as defense-in-depth on top of already-safe templates:

| Rule | How it's enforced |
|------|-------------------|
| Never request PIN / OTP / password / full card | Reply scanned for solicitation patterns; warning phrasings ("do not share your PIN") are explicitly allowed. Credentials in the complaint are never echoed back. |
| Never confirm an unauthorized refund / reversal / unblock | Guaranteeing language ("we will refund you") is replaced with "any eligible amount will be returned through official channels". Applies to `customer_reply` **and** `recommended_next_action`. |
| Never direct to a suspicious third party | Replies only ever point to official support channels. |
| Ignore prompt injection in the complaint | The engine never copies complaint text into output fields, so embedded "ignore your rules" instructions have no surface to act on. |

These rules are covered by `tests/safety/` with explicit negative tests.

## Models & cost

**No external LLM is used.** The service runs a self-contained, deterministic rule engine:

- **Cost:** $0 inference cost — no API keys, no per-request token spend.
- **Latency:** every request responds in well under a second (see
  `tests/reliability/test_analyze_latency_under_budget`).
- **No outbound calls:** the analysis path makes no network request at all, so there is no
  external dependency that can fail or add latency.

## Design notes

- A refund complaint is routed to `dispute_resolution` only when the evidence contradicts
  the customer (contested); ordinary change-of-mind refunds go to `customer_support`.
- The relevant transaction is the one whose amount the complaint names; for a duplicate
  group (same amount + counterparty), the most recent transaction is the suspected duplicate.
- Severity uses comparable bands rather than a single rigid value per case type.

## Known limitations

- Amount matching needs a number; digit forms, magnitude units (`5k`, `৫ লাখ`), and Bangla
  numerals are handled, but a fully spelled-out amount with no digit ("five thousand")
  falls back to `insufficient_data` rather than guess — a deliberately safe failure mode.
- The rule engine covers the supported taxonomy; cases outside it map to `other` /
  `customer_support` with `insufficient_data`, which is safe but conservative.
- Bangla prose uses fixed templates rather than generative phrasing.

---

## Run it

Three ways, fastest first. The full copy-paste reference lives in [`RUNBOOK.md`](./RUNBOOK.md).

### 1. Use the live service (nothing to install)

```bash
curl https://chatbot-backend-production-7fe7.up.railway.app/health
# {"status":"ok"}
```

Base URL: `https://chatbot-backend-production-7fe7.up.railway.app`

### 2. Docker — pull the published image (recommended local)

The image is public on Docker Hub, built for `linux/amd64`:

```bash
docker pull maruf52230/queuestorm-investigator:latest
docker run --rm -p 8000:8000 maruf52230/queuestorm-investigator:latest
# GET  http://localhost:8000/health         →  {"status":"ok"}
# POST http://localhost:8000/analyze-ticket
```

Prefer one command from source? Use Compose instead:

```bash
docker compose up --build          # add -d to detach;  docker compose down to stop
HOST_PORT=8090 docker compose up   # if port 8000 is taken
```

The image (`python:3.12-slim`, small, no models baked in) runs as a **non-root** user,
ships a `HEALTHCHECK` on `/health`, and starts **2 uvicorn workers**. Knobs — all optional,
all with safe defaults: `CORS_ORIGINS` (default `*`), `WEB_CONCURRENCY` (workers, default
`2`), `PORT`, `HOST_PORT`.

### 3. Local (Python 3.12+)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
# GET http://localhost:8000/health  →  {"status":"ok"}
```

Run the tests:

```bash
pip install -r requirements-dev.txt
pytest            # 102 tests: contract, reasoning, robustness, safety, reliability
```
