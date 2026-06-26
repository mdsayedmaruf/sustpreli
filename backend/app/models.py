from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[Message] = Field(..., min_length=1)
    model: str | None = None
    stream: bool = True
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    # When set (and the DB is enabled), the new turn is persisted here.
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    model: str
    conversation_id: str | None = None


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: datetime


class StoredMessage(BaseModel):
    role: str
    content: str
    created_at: datetime


class ConversationDetail(BaseModel):
    id: str
    title: str
    created_at: datetime
    messages: list[StoredMessage]


class CreateConversationRequest(BaseModel):
    title: str = "New chat"
