"""Upload -> OCR -> Claude describe -> NER -> chunk + SBERT -> CLIP -> categorize.

Runs in a FastAPI background task locally, or in a Pub/Sub-triggered Cloud Run worker in the cloud.
Pub/Sub delivers at-least-once, so each run first *claims* the document; duplicates are no-ops
(no double Claude/Vision spend).
"""

import io
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
from PIL import Image, ImageOps
from sqlalchemy import and_, or_, update

from app import classifier, ner, usage, vectors
from app import describe as describe_mod
from app.chunking import build_chunks
from app.config import get_settings
from app.db import SessionLocal
from app.embeddings import clip_image, clip_text, embed_text
from app.models import Category, Chunk, Document, Entity, ImageVector
from app.ocr import extract_text
from app.storage import get_storage

log = logging.getLogger(__name__)
STALE_AFTER = timedelta(minutes=15)  # a "processing" claim older than this is assumed crashed


def _taken_at(img: Image.Image) -> datetime | None:
    try:
        exif = img.getexif()
        raw = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal, DateTime
        return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc) if raw else None
    except (ValueError, TypeError, KeyError):
        return None


def _prepare_image(data: bytes) -> tuple[Image.Image, bytes, datetime | None]:
    """Image for CLIP, a downscaled JPEG for Claude (smaller = fewer tokens), and the EXIF capture date."""
    raw = Image.open(io.BytesIO(data))
    taken = _taken_at(raw)
    img = ImageOps.exif_transpose(raw).convert("RGB")
    side = get_settings().claude_image_max_side
    img.thumbnail((side, side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return img, buf.getvalue(), taken


def _header(doc: Document, fields: list[dict]) -> str:
    lines = [doc.title, doc.summary, doc.caption]
    lines += [f"{f['label']}: {f['value']}" for f in fields]
    return "\n".join(x for x in lines if x)


def remove_vectors(db, doc: Document) -> None:
    chunk_ids = [c for (c,) in db.query(Chunk.id).filter_by(document_id=doc.id)]
    image_ids = [i for (i,) in db.query(ImageVector.id).filter_by(document_id=doc.id)]
    vectors.delete(doc.user_id, chunk_ids, image_ids)
    db.query(ImageVector).filter_by(document_id=doc.id).delete()
    db.query(Chunk).filter_by(document_id=doc.id).delete()
    db.query(Entity).filter_by(document_id=doc.id).delete()


def claim(db, document_id: str) -> bool:
    now = datetime.now(timezone.utc)
    res = db.execute(
        update(Document)
        .where(
            Document.id == document_id,
            or_(
                Document.status == "pending",
                and_(Document.status == "processing",
                     or_(Document.processing_started_at.is_(None), Document.processing_started_at < now - STALE_AFTER)),
            ),
        )
        .values(status="processing", processing_started_at=now, error="")
    )
    db.commit()
    return res.rowcount == 1


def _fail(db, document_id: str, message: str) -> None:
    db.rollback()
    doc = db.get(Document, document_id)
    if doc:
        doc.status, doc.error = "failed", message
        db.commit()


def _amount(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def process_document(document_id: str) -> None:
    db = SessionLocal()
    try:
        if not claim(db, document_id):
            log.info("skip %s: already processed or in progress", document_id)
            return
        doc = db.get(Document, document_id)
        remove_vectors(db, doc)  # idempotent re-processing

        data = get_storage().get(doc.storage_key)
        is_image = doc.mime.startswith("image/")
        img, jpeg, taken = _prepare_image(data) if is_image else (None, None, None)
        doc.taken_at = taken
        notes: list[str] = []  # non-fatal problems shown to the user

        # 1. OCR (Vision is billed per image, so images go through the monthly cap; PDFs are free)
        doc.ocr_text = ""
        try:
            paid = is_image and get_settings().ocr_backend == "vision"
            if paid:
                usage.check_ocr(db)
            doc.ocr_text = extract_text(data, doc.mime).strip()
            if paid:
                usage.record_ocr(db, doc.user_id)
        except usage.LimitExceeded as e:
            notes.append(f"Text not read: {e}")
        except Exception as e:  # OCR failure shouldn't kill the pipeline; photo still indexable visually
            log.warning("OCR failed for %s: %s", doc.id, e)
            notes.append("Text recognition failed.")

        # 2. Claude: title / summary / caption / kind / category pick
        cats = db.query(Category).filter_by(user_id=doc.user_id).all()
        cat_hints = [f"{c.name} ({c.description})" if c.description else c.name for c in cats]
        try:
            d = describe_mod.describe(db, doc.user_id, jpeg, doc.ocr_text, doc.filename, cat_hints)
        except usage.LimitExceeded as e:
            d = None
            notes.append(f"AI description skipped: {e}")
        if d:
            doc.title, doc.summary, doc.caption, doc.kind = d.title, d.summary, d.caption, d.kind
        else:
            doc.title = doc.title or doc.filename.rsplit(".", 1)[0]
            doc.summary = doc.ocr_text[:160]
            doc.kind = "document" if (not is_image or len(doc.ocr_text) > 80) else "photo"

        # 3. NER -> structured fields
        fields = ner.extract_fields(doc.ocr_text)
        for f in fields:
            amount = _amount(f.value) if f.field in ("money", "total") and f.value else None
            db.add(Entity(document_id=doc.id, field=f.field, label=f.label, text=f.text, value=f.value, amount=amount))
        display = ner.summarize_fields(fields)

        # 4. Chunk + Sentence-BERT
        lc_docs = build_chunks(doc.title, _header(doc, display), doc.ocr_text, {"document_id": doc.id})
        rows = [Chunk(document_id=doc.id, user_id=doc.user_id, idx=c.metadata["idx"], text=c.page_content) for c in lc_docs]
        db.add_all(rows)
        db.flush()
        vectors.store_text(doc.user_id, rows, embed_text([r.text for r in rows]) if rows else np.zeros((0, 384)))

        # 5. CLIP (PDFs: CLIP text embedding of the description, same space)
        vec = clip_image(img, fake_hint=f"{doc.caption} {doc.title}") if img is not None else clip_text([f"{doc.title}. {doc.summary}"])
        vec = np.asarray(vec, dtype="float32").reshape(-1)
        iv = ImageVector(document_id=doc.id, user_id=doc.user_id, embedding=vec.tobytes())
        db.add(iv)
        db.flush()
        vectors.store_image(doc.user_id, iv, vec)

        # 6. Category: auto-file when confident, otherwise keep suggestions for the user
        if not doc.category_confirmed:
            classifier.apply(db, doc, classifier.decide(db, doc.user_id, vec, d.category if d else None))

        doc.status, doc.error = "ready", " ".join(notes)
        db.commit()
    except Image.DecompressionBombError:
        _fail(db, document_id, "Image is too large to process.")
    except Exception as e:
        log.exception("ingest failed for %s", document_id)
        _fail(db, document_id, f"Processing failed ({e.__class__.__name__}). Try Re-process.")
    finally:
        db.close()
