import json
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from . import db
from .config import get_settings
from .models import (
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationSummary,
    CreateConversationRequest,
    StoredMessage,
)
from .openrouter import OpenRouterError, chat_completion, stream_chat_completion

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield


app = FastAPI(title=settings.app_title, version="1.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_session() -> AsyncSession:
    if not db.enabled or db.SessionLocal is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    async with db.SessionLocal() as session:
        yield session


@app.get("/")
def root():
    return {"status": "ok", "service": settings.app_title}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "model": settings.openrouter_model,
        "configured": bool(settings.openrouter_api_key),
        "database": db.enabled,
    }


# ---------------------------------------------------------------------------
# Conversation history (only available when the DB is configured)
# ---------------------------------------------------------------------------


@app.post("/api/conversations", response_model=ConversationSummary)
async def create_conversation(
    req: CreateConversationRequest, session: AsyncSession = Depends(get_session)
):
    convo = await db.create_conversation(session, title=req.title)
    return ConversationSummary(id=convo.id, title=convo.title, created_at=convo.created_at)


@app.get("/api/conversations", response_model=list[ConversationSummary])
async def list_conversations(session: AsyncSession = Depends(get_session)):
    convos = await db.list_conversations(session)
    return [
        ConversationSummary(id=c.id, title=c.title, created_at=c.created_at)
        for c in convos
    ]


@app.get("/api/conversations/{convo_id}", response_model=ConversationDetail)
async def get_conversation(convo_id: str, session: AsyncSession = Depends(get_session)):
    convo = await db.get_conversation_with_messages(session, convo_id)
    if convo is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return ConversationDetail(
        id=convo.id,
        title=convo.title,
        created_at=convo.created_at,
        messages=[
            StoredMessage(role=m.role, content=m.content, created_at=m.created_at)
            for m in convo.messages
        ],
    )


@app.delete("/api/conversations/{convo_id}")
async def delete_conversation(convo_id: str, session: AsyncSession = Depends(get_session)):
    ok = await db.delete_conversation(session, convo_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"status": "deleted", "id": convo_id}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


async def _persist_turn(convo_id: str | None, user_content: str, assistant_content: str):
    """Save the latest user + assistant messages, if the DB is enabled."""
    if not convo_id or not db.enabled or db.SessionLocal is None:
        return
    async with db.SessionLocal() as session:
        convo = await db.get_conversation(session, convo_id)
        if convo is None:
            return
        await db.add_message(session, convo_id, "user", user_content)
        await db.add_message(session, convo_id, "assistant", assistant_content)
        # Title the conversation from its first user message.
        if convo.title == "New chat" and user_content.strip():
            convo.title = user_content.strip()[:60]
            await session.commit()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Non-streaming chat endpoint. Returns the full reply at once."""
    messages = [m.model_dump() for m in req.messages]
    try:
        reply, model = await chat_completion(
            settings, messages, model=req.model, temperature=req.temperature
        )
    except OpenRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await _persist_turn(req.conversation_id, messages[-1]["content"], reply)
    return ChatResponse(reply=reply, model=model, conversation_id=req.conversation_id)


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streaming chat endpoint using Server-Sent Events (SSE)."""
    messages = [m.model_dump() for m in req.messages]

    async def event_generator():
        collected: list[str] = []
        try:
            async for chunk in stream_chat_completion(
                settings, messages, model=req.model, temperature=req.temperature
            ):
                collected.append(chunk)
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        except OpenRouterError as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        await _persist_turn(req.conversation_id, messages[-1]["content"], "".join(collected))
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
