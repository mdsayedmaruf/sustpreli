"""QueueStorm Investigator — FastAPI service.

Exposes the two endpoints the judge harness exercises (problem.md §4):
  * GET  /health         → {"status":"ok"} (readiness, no dependencies)
  * POST /analyze-ticket → structured case analysis (§6)

The service is intentionally self-contained: no database, no outbound call on the
default path, so /health is instant and /analyze-ticket is deterministic and fast.
All error paths return non-sensitive JSON — the process never crashes or leaks a
stack trace, token, or secret (§4.1, §9.2).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .reasoning import analyze, safe_fallback
from .schemas import AnalyzeTicketRequest, AnalyzeTicketResponse

logger = logging.getLogger("queuestorm")

settings = get_settings()

app = FastAPI(title="QueueStorm Investigator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health & root
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    """Readiness probe. Exactly ``{"status":"ok"}``, no extra keys, no I/O."""
    return {"status": "ok"}


@app.get("/")
def root():
    return {"status": "ok", "service": "QueueStorm Investigator"}


# ---------------------------------------------------------------------------
# Main analysis endpoint
# ---------------------------------------------------------------------------


@app.post("/analyze-ticket", response_model=AnalyzeTicketResponse)
def analyze_ticket(req: AnalyzeTicketRequest):
    """Analyse one support ticket and return spec-exact JSON (§6).

    Returns 422 for a schema-valid but semantically empty complaint. Any
    unexpected internal error degrades to a safe, schema-valid fallback (200,
    escalated for manual review) rather than a 5xx — a correct-but-crashing
    service still loses points (§14.2 Performance & Reliability).
    """
    if not req.complaint or not req.complaint.strip():
        return JSONResponse(
            status_code=422,
            content={"error": "The 'complaint' field must not be empty."},
        )

    try:
        result = analyze(req)
        return result
    except Exception:  # pragma: no cover - safety net, must never leak internals
        logger.exception("analyze() failed for ticket_id=%s", req.ticket_id)
        bangla = (req.language or "").lower() in {"bn", "mixed"}
        return safe_fallback(req.ticket_id, bangla=bangla)


# ---------------------------------------------------------------------------
# Error handlers — non-sensitive JSON, never a stack trace (§4.1, §9.2)
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError):
    """Malformed input (invalid JSON / missing required fields) → 400 (§4.1).

    We surface only the field locations, never the raw payload, so nothing
    sensitive a client sent is reflected back.
    """
    fields = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        if loc:
            fields.append(loc)
    detail = "Malformed request body."
    if fields:
        detail = f"Malformed or missing fields: {', '.join(sorted(set(fields)))}."
    return JSONResponse(status_code=400, content={"error": detail})


@app.exception_handler(Exception)
async def on_unhandled_error(request: Request, exc: Exception):
    """Any other failure → safe 500, no stack trace / token / secret leaked."""
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "An internal error occurred while processing the request."},
    )
