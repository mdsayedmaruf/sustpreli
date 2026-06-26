# RUNBOOK — QueueStorm Investigator

A stranger can bring this service up by copy-pasting the steps below. The service has
**no required external dependencies** (no database, no API key) on the analysis path.

> **Live service (no setup):** <https://sustpreli-production-56d0.up.railway.app>
> — `/health` returns `{"status":"ok"}`. Public Docker image:
> `docker pull maruf52230/queuestorm-investigator:latest`

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

## Option B — Docker (recommended)

**Pull the published image (no build needed):**

```bash
docker pull maruf52230/queuestorm-investigator:latest
docker run --rm -p 8000:8000 maruf52230/queuestorm-investigator:latest
# /health and /analyze-ticket now respond on http://localhost:8000
```

**With Docker Compose (build from source, one command, from the repo root):**

```bash
docker compose up --build          # foreground; Ctrl+C to stop
docker compose up -d --build       # detached
docker compose down                # stop and remove
# /health and /analyze-ticket now respond on http://localhost:8000
```

If port 8000 is already in use on your host, publish a different one:

```bash
HOST_PORT=8090 docker compose up --build   # now on http://localhost:8090
```

**Without Compose (plain Docker):**

```bash
docker build -t queuestorm-investigator ./backend
docker run --rm -p 8000:8000 queuestorm-investigator
```

The image is based on `python:3.12-slim` and stays well under the 5 GB guidance; no models
are baked in. It runs as a **non-root** user, declares a `HEALTHCHECK` on `/health`, and
starts **2 uvicorn workers** by default (override with `-e WEB_CONCURRENCY=4`).

Configuration (all optional, all default to a working LLM-free setup):

| Variable | Default | Purpose |
|----------|---------|---------|
| `CORS_ORIGINS` | `*` | Comma-separated allowlist, or `*`. Credentials are auto-disabled with `*`. |
| `WEB_CONCURRENCY` | `2` | Number of uvicorn workers. |
| `PORT` | `8000` | Port the app binds inside the container (most PaaS inject this). |
| `HOST_PORT` | `8000` | Host port published by `docker compose` (compose only). |

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
# 102 passed  (contract, 10 sample cases, reasoning robustness, safety, reliability)
```

## Troubleshooting

- **`/health` not returning `{"status":"ok"}`** — confirm you are hitting the root path
  `/health`, not `/api/health`.
- **Port already in use** — change `--port` (local) or the published port (`-p`).
- **Bangla replies show as boxes** — that's a terminal font issue; the JSON is correct
  UTF-8 (see `sample_output.json`).
