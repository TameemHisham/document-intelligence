"""Hybrid semantic search.

query --(Gemini / rules)--> filters + semantic text
semantic text --SBERT--> chunk similarity  ┐
semantic text --CLIP---> image similarity  ┴--> Reciprocal Rank Fusion
filters (date, kind, category, amount) are SQL conditions: on pgvector they run inside the same
query as the vector similarity; on FAISS they filter over-fetched candidates.
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import vectors
from app.config import get_settings
from app.embeddings import clip_text, embed_text
from app.models import Category, Chunk, Document, Entity, ImageVector
from app.query_parser import QueryFilters

RRF_K = 60
CANDIDATES = 200


@dataclass
class Hit:
    document: Document
    score: float
    snippet: str
    matched: list[str] = field(default_factory=list)  # "text", "visual", "filters"


def doc_date():
    return func.coalesce(Document.taken_at, Document.created_at)


def conditions(
    db: Session, user_id: str, f: QueryFilters | None, kind: str | None, category_id: str | None,
    document_ids: set[str] | None,
) -> list:
    conds = [Document.user_id == user_id, Document.status == "ready"]
    kind = kind or (f.kind if f else None)
    if kind:
        conds.append(Document.kind == kind)
    if category_id:
        conds.append(Document.category_id == category_id)
    elif f and f.category:
        cat = db.query(Category).filter(Category.user_id == user_id, func.lower(Category.name) == f.category.lower()).first()
        if cat:
            conds.append(Document.category_id == cat.id)
    if document_ids is not None:
        conds.append(Document.id.in_(document_ids))
    if f and f.date_from:
        conds.append(doc_date() >= datetime.combine(f.date_from, time.min, tzinfo=timezone.utc))
    if f and f.date_to:
        conds.append(doc_date() <= datetime.combine(f.date_to, time.max, tzinfo=timezone.utc))
    for bound, op in ((f.min_amount if f else None, "ge"), (f.max_amount if f else None, "le")):
        if bound is not None:
            amt = Entity.amount >= bound if op == "ge" else Entity.amount <= bound
            conds.append(Document.id.in_(select(Entity.document_id).where(Entity.field.in_(("total", "money")), amt)))
    return conds


def search(
    db: Session,
    user_id: str,
    query: str,
    limit: int = 30,
    kind: str | None = None,
    category_id: str | None = None,
    document_ids: set[str] | None = None,
    filters: QueryFilters | None = None,
) -> list[Hit]:
    s = get_settings()
    semantic = (filters.semantic_query if filters else query).strip()
    conds = conditions(db, user_id, filters, kind, category_id, document_ids)

    if not semantic:  # filter-only query, e.g. "photos from last summer"
        if not (filters and filters.has_filters()):
            return []
        docs = db.query(Document).filter(*conds).order_by(doc_date().desc()).limit(limit).all()
        return [Hit(d, 0.0, d.summary, ["filters"]) for d in docs]

    # Text: chunk hits -> best chunk per document
    text_hits = [(c, sc) for c, sc in vectors.search_text(db, user_id, embed_text([semantic])[0], CANDIDATES, conds)
                 if sc >= s.text_min_score]
    chunks = {c.id: c for c in db.query(Chunk).filter(Chunk.id.in_([c for c, _ in text_hits]))} if text_hits else {}
    text_rank: dict[str, tuple[int, str]] = {}
    for cid, _ in text_hits:
        c = chunks.get(cid)
        if c and c.document_id not in text_rank:
            text_rank[c.document_id] = (len(text_rank), c.text)

    # Visual: CLIP text query vs image embeddings. CLIP similarities are compressed (~0.18-0.35),
    # so keep only hits near the best one as well as above an absolute floor.
    img_hits = vectors.search_images(db, user_id, clip_text([semantic])[0], CANDIDATES, conds)
    best = img_hits[0][1] if img_hits else 0.0
    img_hits = [(i, sc) for i, sc in img_hits if sc >= s.image_min_score and sc >= best - s.image_relative_margin]
    ivs = {i.id: i.document_id for i in db.query(ImageVector).filter(ImageVector.id.in_([i for i, _ in img_hits]))} if img_hits else {}
    img_rank: dict[str, int] = {}
    for iid, _ in img_hits:
        did = ivs.get(iid)
        if did and did not in img_rank:
            img_rank[did] = len(img_rank)

    fused: dict[str, float] = {}
    for did, (r, _) in text_rank.items():
        fused[did] = fused.get(did, 0) + 1 / (RRF_K + r)
    for did, r in img_rank.items():
        fused[did] = fused.get(did, 0) + 1 / (RRF_K + r)
    if not fused:
        return []

    # FAISS candidates weren't filtered yet; on pgvector this is a cheap re-check.
    docs = db.query(Document).filter(Document.id.in_(fused), *conds).all()
    hits = [
        Hit(d, fused[d.id], text_rank.get(d.id, (0, d.summary))[1],
            [m for m, ok in (("text", d.id in text_rank), ("visual", d.id in img_rank)) if ok])
        for d in docs
    ]
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]
