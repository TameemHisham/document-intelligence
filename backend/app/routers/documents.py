import io
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import check_file_token, current_user
from app.config import get_settings
from app.db import get_db
from app import classifier
from app.ingest import remove_vectors
from app.search import doc_date
from app.tasks import enqueue
from app.models import Category, Document, User
from app.ratelimit import limit
from app.schemas import BulkIn, BulkOut, DocumentDetail, DocumentOut, DocumentPatch, doc_detail, doc_out
from app.storage import get_storage

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}
PIL_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}


def sniff_mime(data: bytes) -> str | None:
    """Trust the bytes, not the client's Content-Type."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = im.format
            im.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError):
        return None
    return PIL_FORMATS.get(fmt or "")


def owned(db: Session, user: User, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.user_id != user.id:
        raise HTTPException(404, "document not found")
    return doc


@router.post("", response_model=list[DocumentOut])
async def upload(
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    user: User = Depends(limit("upload")),
    db: Session = Depends(get_db),
):
    s = get_settings()
    if len(files) > s.max_files_per_request:
        raise HTTPException(400, f"Upload at most {s.max_files_per_request} files at a time.")
    total = db.query(func.count(Document.id)).filter(Document.user_id == user.id).scalar()
    if total + len(files) > s.max_documents_per_user:
        raise HTTPException(429, f"Library limit of {s.max_documents_per_user} items reached.")
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today = db.query(func.count(Document.id)).filter(Document.user_id == user.id, Document.created_at >= day_start).scalar()
    if today + len(files) > s.max_uploads_per_day:
        raise HTTPException(429, f"Daily upload limit of {s.max_uploads_per_day} reached. Try again tomorrow.")

    max_bytes = s.max_upload_mb * 1024 * 1024
    validated = []
    for f in files:  # validate everything first so a bad file doesn't leave a half-finished batch
        data = await f.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(413, f"{f.filename}: larger than {s.max_upload_mb} MB")
        mime = sniff_mime(data)
        if mime not in ALLOWED:
            raise HTTPException(415, f"{f.filename}: not a supported image or PDF")
        validated.append((f, data, mime))

    created = []
    for f, data, mime in validated:
        doc = Document(user_id=user.id, filename=Path(f.filename or "upload").name[:200], mime=mime, storage_key="")
        db.add(doc)
        db.flush()
        doc.storage_key = f"{user.id}/{doc.id}{mimetypes.guess_extension(mime) or ''}"
        get_storage().put(doc.storage_key, data, mime)
        created.append(doc)
    db.commit()
    enqueue(background, [d.id for d in created])
    return [doc_out(d) for d in created]


@router.get("", response_model=list[DocumentOut])
def list_documents(
    category_id: str | None = None,
    kind: str | None = None,
    favorite: bool | None = None,
    status: str | None = None,
    uncategorized: bool = False,
    limit: int = Query(100, le=500),
    offset: int = 0,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Document).filter(Document.user_id == user.id)
    if uncategorized:
        q = q.filter(Document.category_id.is_(None), Document.status == "ready")
    if category_id:
        q = q.filter(Document.category_id == category_id)
    if kind:
        q = q.filter(Document.kind == kind)
    if favorite is not None:
        q = q.filter(Document.favorite.is_(favorite))
    if status:
        q = q.filter(Document.status == status)
    return [doc_out(d) for d in q.order_by(doc_date().desc(), Document.created_at.desc()).offset(offset).limit(limit)]


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return doc_detail(owned(db, user, document_id))


@router.patch("/{document_id}", response_model=DocumentDetail)
def patch_document(document_id: str, body: DocumentPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = owned(db, user, document_id)
    if body.title is not None:
        doc.title = body.title.strip()[:200]
    if body.favorite is not None:
        doc.favorite = body.favorite
    if body.new_category_name:
        file_into(doc, classifier.get_or_create(db, user.id, body.new_category_name, source="ai"))
    elif body.category_id is not None:
        file_into(doc, owned_category(db, user, body.category_id))
    db.commit()
    return doc_detail(doc)


def owned_category(db: Session, user: User, category_id: str) -> Category:
    cat = db.get(Category, category_id)
    if cat is None or cat.user_id != user.id:
        raise HTTPException(404, "category not found")
    return cat


def file_into(doc: Document, cat: Category) -> None:
    """User-chosen category: confirmed labels become training data for the classifier."""
    doc.category_id, doc.category_confirmed, doc.category_method, doc.category_confidence = cat.id, True, "user", 1.0
    doc.pending_category = ""


@router.post("/bulk", response_model=BulkOut)
def bulk(body: BulkIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    docs = db.query(Document).filter(Document.id.in_(body.document_ids), Document.user_id == user.id).all()
    if body.action == "categorize":
        if not body.category_id:
            raise HTTPException(400, "category_id required")
        cat = owned_category(db, user, body.category_id)
        for d in docs:
            file_into(d, cat)
    elif body.action == "accept_suggestions":  # file each item into its top suggestion
        for d in docs:
            top = doc_out(d).suggestions[:1]
            if d.category_id is None and top:
                s = top[0]
                cat = db.get(Category, s.category_id) if s.category_id else classifier.get_or_create(db, user.id, s.name)
                if cat is not None and cat.user_id == user.id:
                    file_into(d, cat)
            elif d.category_id:
                d.category_confirmed = True
    elif body.action in ("favorite", "unfavorite"):
        for d in docs:
            d.favorite = body.action == "favorite"
    elif body.action == "delete":
        for d in docs:
            remove_vectors(db, d)
            get_storage().delete(d.storage_key)
            db.delete(d)
    db.commit()
    return BulkOut(updated=len(docs))


@router.post("/{document_id}/confirm-category", response_model=DocumentDetail)
def confirm_category(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = owned(db, user, document_id)
    if doc.category_id is None:
        raise HTTPException(400, "document has no category to confirm")
    doc.category_confirmed = True
    db.commit()
    return doc_detail(doc)


@router.post("/{document_id}/reprocess", response_model=DocumentOut)
def reprocess(document_id: str, background: BackgroundTasks, user: User = Depends(limit("reprocess")), db: Session = Depends(get_db)):
    doc = owned(db, user, document_id)
    if doc.status in ("pending", "processing"):
        raise HTTPException(409, "Already processing.")
    doc.status = "pending"
    db.commit()
    enqueue(background, [doc.id])
    return doc_out(doc)


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = owned(db, user, document_id)
    remove_vectors(db, doc)
    get_storage().delete(doc.storage_key)
    db.delete(doc)
    db.commit()


@router.get("/{document_id}/file")
def get_file(document_id: str, t: str, db: Session = Depends(get_db)):
    user_id = check_file_token(t, document_id)
    doc = db.get(Document, document_id)
    if doc is None or doc.user_id != user_id:
        raise HTTPException(404)
    return Response(
        get_storage().get(doc.storage_key),
        media_type=doc.mime,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
