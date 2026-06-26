# RUNBOOK — QueueStorm Investigator

A stranger can bring this service up by copy-pasting the steps below. The service has
**no required external dependencies** (no database, no API key) on the analysis path.

## Requirements

- Python 3.12+ (tested on 3.12–3.14), **or** Docker.

## Option A — Local (Python)

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Verify:

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl -s http://localhost:8000/analyze-ticket -H "Content-Type: application/json" -d '{
  "ticket_id":"TKT-001",
  "complaint":"I sent 5000 taka to a wrong number around 2pm today.",
  "transaction_history":[{"transaction_id":"TXN-9101","timestamp":"2026-04-14T14:08:22Z","type":"transfer","amount":5000,"counterparty":"+8801719876543","status":"completed"}]
}'
```

## Option B — Docker

```bash
cd backend
docker build -t queuestorm-investigator .
docker run --rm -p 8000:8000 queuestorm-investigator
# /health and /analyze-ticket now respond on http://localhost:8000
```

The image is based on `python:3.12-slim` and stays well under the 5 GB guidance; no
models are baked in.

## Option C — Deploy (Render / Railway / Fly / any PaaS)

The service reads `$PORT` (the Dockerfile already does `--port ${PORT:-8000}`):

- **Render:** New Web Service → Docker → root `backend/`. No env vars required.
- **Railway/Fly:** point at `backend/Dockerfile`. Health check path: `/health`.

No environment variables are required to run. Optional ones are listed in
`backend/.env.example` (all default to a fully working, LLM-free configuration).

## Run the tests

```bash
# from repo root
pip install -r backend/requirements.txt -r requirements-dev.txt
pytest
# 92 passed  (contract, 10 sample cases, safety, reliability)
```

## Troubleshooting

- **`/health` not returning `{"status":"ok"}`** — confirm you are hitting the root path
  `/health`, not `/api/health`.
- **Port already in use** — change `--port` (local) or the published port (`-p`).
- **Bangla replies show as boxes** — that's a terminal font issue; the JSON is correct
  UTF-8 (see `sample_output.json`).
