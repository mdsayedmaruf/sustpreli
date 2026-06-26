"""Optional PostgreSQL persistence for chat history.

If ``DATABASE_URL`` is not set, ``enabled`` is False and the app runs without
any database. Designed to work with Neon (serverless Postgres) via asyncpg.
"""

import ssl
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import ForeignKey, String, Text, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    selectinload,
)

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _new_id() -> str:
    return str(uuid4())


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


def _normalize_url(url: str) -> str:
    """Make a SQLAlchemy async URL and drop query params asyncpg rejects.

    asyncpg does not understand libpq params like ``sslmode`` / ``channel_binding``
    in the URL; SSL is configured via connect_args instead.
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query)
        if k not in ("sslmode", "channel_binding")
    ]
    return urlunsplit(parts._replace(query=urlencode(query)))


_settings = get_settings()
enabled: bool = bool(_settings.database_url)

engine = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None

if enabled:
    engine = create_async_engine(
        _normalize_url(_settings.database_url),
        pool_pre_ping=True,
        connect_args={"ssl": ssl.create_default_context()},
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create tables if they don't exist. No-op when the DB is disabled."""
    if not enabled or engine is None:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def create_conversation(session: AsyncSession, title: str = "New chat") -> Conversation:
    convo = Conversation(title=title[:200] or "New chat")
    session.add(convo)
    await session.commit()
    await session.refresh(convo)
    return convo


async def list_conversations(session: AsyncSession) -> list[Conversation]:
    result = await session.execute(
        select(Conversation).order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


async def get_conversation(session: AsyncSession, convo_id: str) -> Conversation | None:
    return await session.get(Conversation, convo_id)


async def get_conversation_with_messages(
    session: AsyncSession, convo_id: str
) -> Conversation | None:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.id == convo_id)
        .options(selectinload(Conversation.messages))
    )
    return result.scalar_one_or_none()


async def add_message(
    session: AsyncSession, convo_id: str, role: str, content: str
) -> Message:
    msg = Message(conversation_id=convo_id, role=role, content=content)
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


async def delete_conversation(session: AsyncSession, convo_id: str) -> bool:
    convo = await session.get(Conversation, convo_id)
    if convo is None:
        return False
    await session.delete(convo)
    await session.commit()
    return True
