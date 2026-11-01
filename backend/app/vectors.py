"""Vector storage behind one interface.

- faiss    (local dev): per-user FAISS files; SQL filters applied to over-fetched candidates.
- pgvector (cloud):     embeddings live in Postgres next to the metadata, so vector similarity and
                        SQL filters (date, kind, category, amount) run in ONE query.
"""

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PGVECTOR, Chunk, Document, ImageVector
from app.vector_index import UserIndex


def store_text(user_id: str, rows: list[Chunk], vecs: np.ndarray) -> None:
    """Call after flush (rows have ids)."""
    if not rows:
        return
    if PGVECTOR:
        for r, v in zip(rows, vecs):
            r.vec = v.tolist()
    else:
        UserIndex(user_id, "text").add([r.id for r in rows], vecs)


def store_image(user_id: str, iv: ImageVector, vec: np.ndarray) -> None:
    if PGVECTOR:
        iv.vec = vec.reshape(-1).tolist()
    else:
        UserIndex(user_id, "image").add([iv.id], vec.reshape(1, -1))


def delete(user_id: str, chunk_ids: list[int], image_ids: list[int]) -> None:
    if PGVECTOR:
        return  # rows are deleted with their embeddings
    UserIndex(user_id, "text").remove(chunk_ids)
    UserIndex(user_id, "image").remove(image_ids)


def search_text(db: Session, user_id: str, q: np.ndarray, k: int, doc_filter=None) -> list[tuple[int, float]]:
    """Returns [(chunk_id, cosine_similarity)] best first. `doc_filter`: SQL conditions on Document."""
    if not PGVECTOR:
        return UserIndex(user_id, "text").search(q, k)
    dist = Chunk.vec.cosine_distance(q.tolist())
    stmt = (
        select(Chunk.id, (1 - dist).label("sim"))
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.user_id == user_id, Document.status == "ready", *(doc_filter or []))
        .order_by(dist)
        .limit(k)
    )
    return [(i, float(s)) for i, s in db.execute(stmt)]


def search_images(db: Session, user_id: str, q: np.ndarray, k: int, doc_filter=None) -> list[tuple[int, float]]:
    if not PGVECTOR:
        return UserIndex(user_id, "image").search(q, k)
    dist = ImageVector.vec.cosine_distance(q.tolist())
    stmt = (
        select(ImageVector.id, (1 - dist).label("sim"))
        .join(Document, Document.id == ImageVector.document_id)
        .where(ImageVector.user_id == user_id, Document.status == "ready", *(doc_filter or []))
        .order_by(dist)
        .limit(k)
    )
    return [(i, float(s)) for i, s in db.execute(stmt)]


def search_chunks_subset(db: Session, user_id: str, q: np.ndarray, chunk_ids: list[int], k: int) -> list[tuple[int, float]]:
    if not chunk_ids:
        return []
    if not PGVECTOR:
        return UserIndex(user_id, "text").search_subset(q, chunk_ids, k)
    dist = Chunk.vec.cosine_distance(q.tolist())
    stmt = select(Chunk.id, (1 - dist)).where(Chunk.id.in_(chunk_ids), Chunk.user_id == user_id).order_by(dist).limit(k)
    return [(i, float(s)) for i, s in db.execute(stmt)]
