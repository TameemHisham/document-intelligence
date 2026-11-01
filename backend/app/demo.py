"""Public demo: one-click guest sandboxes.

The owner curates a *template* library (signing in to it via "Edit demo library"). Each guest gets
a private copy: rows are cloned, files are shared (never re-uploaded), text embeddings are recomputed
locally and CLIP embeddings copied - so creating a sandbox costs no API calls. Guests expire after
DEMO_TTL_HOURS and are purged lazily.
"""

import logging
import shutil
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import vectors
from app.config import get_settings
from app.embeddings import embed_text
from app.models import Category, Chunk, Document, Entity, ImageVector, Project, User
from app.storage import get_storage

log = logging.getLogger(__name__)
TEMPLATE_SUB = "demo:template"


def template_user(db: Session) -> User:
    user = db.query(User).filter_by(google_sub=TEMPLATE_SUB).one_or_none()
    if user is None:
        from app.auth import DEFAULT_CATEGORIES

        user = User(google_sub=TEMPLATE_SUB, email="demo-library@template", name="Demo library")
        db.add(user)
        db.flush()
        for name, color in DEFAULT_CATEGORIES:
            db.add(Category(user_id=user.id, name=name, color=color, source="default"))
        db.commit()
    return user


def guests_created_today(db: Session) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(func.count(User.id)).filter(User.is_guest.is_(True), User.created_at >= start).scalar()


def create_guest(db: Session) -> User:
    s = get_settings()
    guest = User(
        google_sub=f"guest:{uuid.uuid4().hex}",
        email="guest@demo",
        name="Guest",
        is_guest=True,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=s.demo_ttl_hours),
    )
    db.add(guest)
    db.flush()
    clone_library(db, template_user(db), guest)
    db.commit()
    return guest


def clone_library(db: Session, src: User, dst: User) -> None:
    cat_map: dict[str, str] = {}
    for c in db.query(Category).filter_by(user_id=src.id).order_by(Category.created_at):
        nc = Category(user_id=dst.id, name=c.name, description=c.description, color=c.color, source=c.source)
        db.add(nc)
        db.flush()
        cat_map[c.id] = nc.id

    doc_map: dict[str, str] = {}
    new_chunks: list[Chunk] = []
    docs = db.query(Document).filter_by(user_id=src.id, status="ready").all()
    for d in docs:
        nd = Document(
            user_id=dst.id, filename=d.filename, mime=d.mime, storage_key=d.storage_key, storage_shared=True,
            kind=d.kind, status="ready", title=d.title, summary=d.summary, caption=d.caption, ocr_text=d.ocr_text,
            taken_at=d.taken_at, category_id=cat_map.get(d.category_id) if d.category_id else None,
            category_confidence=d.category_confidence, category_method=d.category_method,
            category_confirmed=d.category_confirmed, suggestions="[]", pending_category=d.pending_category,
            favorite=d.favorite, created_at=d.created_at,
        )
        db.add(nd)
        db.flush()
        doc_map[d.id] = nd.id
        for e in d.entities:
            db.add(Entity(document_id=nd.id, field=e.field, label=e.label, text=e.text, value=e.value, amount=e.amount))
        for c in db.query(Chunk).filter_by(document_id=d.id).order_by(Chunk.idx):
            nc = Chunk(document_id=nd.id, user_id=dst.id, idx=c.idx, text=c.text)
            db.add(nc)
            new_chunks.append(nc)
        iv = db.query(ImageVector).filter_by(document_id=d.id).one_or_none()
        if iv:
            niv = ImageVector(document_id=nd.id, user_id=dst.id, embedding=iv.embedding)
            db.add(niv)
            db.flush()
            vectors.store_image(dst.id, niv, np.frombuffer(iv.embedding, dtype="float32"))

    db.flush()
    if new_chunks:  # local SBERT, no API cost
        vectors.store_text(dst.id, new_chunks, embed_text([c.text for c in new_chunks]))

    for p in db.query(Project).filter_by(user_id=src.id):
        db.add(Project(user_id=dst.id, name=p.name,
                       documents=[db.get(Document, doc_map[d.id]) for d in p.documents if d.id in doc_map]))


def purge_expired(db: Session) -> int:
    now = datetime.now(timezone.utc)
    expired = db.query(User).filter(User.is_guest.is_(True), User.expires_at < now).limit(100).all()
    for u in expired:
        delete_user(db, u)
    if expired:
        db.commit()
        log.info("purged %d expired demo sandboxes", len(expired))
    return len(expired)


def delete_user(db: Session, user: User) -> None:
    storage = get_storage()
    for d in db.query(Document).filter_by(user_id=user.id):
        if not d.storage_shared:
            storage.delete(d.storage_key)
    db.query(Chunk).filter_by(user_id=user.id).delete()
    db.query(ImageVector).filter_by(user_id=user.id).delete()
    for model in (Project, Document, Category):
        for row in db.query(model).filter_by(user_id=user.id):
            db.delete(row)
    db.delete(user)
    shutil.rmtree(get_settings().data_dir / "indexes" / user.id, ignore_errors=True)


def guest_limits(db: Session, user: User) -> dict:
    from app.models import ApiUsage

    s = get_settings()
    asked = db.query(func.count(ApiUsage.id)).filter(ApiUsage.user_id == user.id, ApiUsage.kind == "ask").scalar()
    uploaded = db.query(func.count(Document.id)).filter(Document.user_id == user.id, Document.storage_shared.is_(False)).scalar()
    return {
        "questions_left": max(0, s.demo_guest_questions - asked),
        "uploads_left": max(0, s.demo_guest_uploads - uploaded),
        "expires_at": user.expires_at,
    }
