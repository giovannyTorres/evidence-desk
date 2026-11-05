import datetime as dt
import uuid
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from pgvector.sqlalchemy import Vector
from .config import settings


def uid() -> str:
    return str(uuid.uuid4())


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    org: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    mode: Mapped[str] = mapped_column(String, default='DEMO')
    password_hash: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)


class LoginSession(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    mode: Mapped[str] = mapped_column(String, default='DEMO')
    expires: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = 'documents'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    org: Mapped[str] = mapped_column(String, index=True)
    mode: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    current_version: Mapped[int] = mapped_column(Integer, default=1)


class Version(Base):
    __tablename__ = 'versions'
    __table_args__ = (UniqueConstraint('document_id', 'number'),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String)
    content_hash: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)  # base64, bounded upload; no unprotected filesystem URL
    status: Mapped[str] = mapped_column(String, default='queued')
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Chunk(Base):
    __tablename__ = 'chunks'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    version_id: Mapped[str] = mapped_column(ForeignKey('versions.id', ondelete='CASCADE'), index=True)
    location: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(), nullable=True)


class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    version_id: Mapped[str] = mapped_column(ForeignKey('versions.id', ondelete='CASCADE'), unique=True)
    state: Mapped[str] = mapped_column(String, default='queued')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    org: Mapped[str] = mapped_column(String, index=True)
    mode: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    cancelled: Mapped[bool] = mapped_column(default=False)
    busy: Mapped[bool] = mapped_column(default=False)
    lease_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    created: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


engine = create_engine(settings().database_url, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)
