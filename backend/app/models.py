import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Table, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.db import Base

PGVECTOR = get_settings().vector_backend == "pgvector"
if PGVECTOR:
    from pgvector.sqlalchemy import Vector


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


project_documents = Table(
    "project_documents",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("document_id", ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    google_sub: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String, default="")
    picture: Mapped[str] = mapped_column(String, default="")
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False)  # demo sandbox user
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")  # helps the AI classify into custom categories
    color: Mapped[str] = mapped_column(String, default="#2f6b45")
    source: Mapped[str] = mapped_column(String, default="user")  # "user" | "ai" | "default"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String)
    mime: Mapped[str] = mapped_column(String)
    storage_key: Mapped[str] = mapped_column(String)
    storage_shared: Mapped[bool] = mapped_column(Boolean, default=False)  # demo copy: file belongs to the template
    kind: Mapped[str] = mapped_column(String, default="photo")  # "photo" | "document"
    status: Mapped[str] = mapped_column(String, default="pending")  # pending | processing | ready | failed
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)  # EXIF
    category_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    category_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    category_method: Mapped[str] = mapped_column(String, default="")  # classifier | claude | zero-shot | ai-group | user
    category_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    suggestions: Mapped[str] = mapped_column(Text, default="[]")  # JSON: [{category_id|null, name, score, source}]
    pending_category: Mapped[str] = mapped_column(String, default="")  # AI-proposed new category awaiting a group
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    category: Mapped[Category | None] = relationship()
    entities: Mapped[list["Entity"]] = relationship(cascade="all, delete-orphan", order_by="Entity.id")
    projects: Mapped[list["Project"]] = relationship(secondary=project_documents, back_populates="documents")


class Entity(Base):
    """Structured fields pulled out of OCR text by spaCy NER + rules."""

    __tablename__ = "entities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String, index=True)  # e.g. expiry_date, total, org, person
    label: Mapped[str] = mapped_column(String)  # spaCy label or RULE
    text: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(String, default="")  # normalized (ISO date, number)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)  # numeric value for money/total filters


class Chunk(Base):
    """Text chunk. FAISS mode: id is the FAISS id. pgvector mode: embedding lives in `vec`."""

    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    idx: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    if PGVECTOR:
        vec: Mapped[Any] = mapped_column(Vector(384), nullable=True)


class ImageVector(Base):
    """CLIP embedding (bytes kept for classifier training). FAISS id = row id; pgvector: `vec`."""

    __tablename__ = "image_vectors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), unique=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)
    if PGVECTOR:
        vec: Mapped[Any] = mapped_column(Vector(512), nullable=True)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    documents: Mapped[list[Document]] = relationship(secondary=project_documents, back_populates="projects")


class ApiUsage(Base):
    """One row per paid API call, for budget enforcement."""

    __tablename__ = "api_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, index=True)  # describe | ask | ocr | parse
    guest: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # counts against the demo budget
    model: Mapped[str] = mapped_column(String)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
