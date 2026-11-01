"""Category assignment, suggestions and grouping.

For each new item we build ranked *suggestions* from three signals:
  1. learned  - scikit-learn LogisticRegression on CLIP embeddings of items the user confirmed
  2. claude   - Claude's category pick (an existing category, or a proposed new name)
  3. zero-shot- CLIP similarity between the image and "a photo of <category: description>"
The top suggestion is auto-applied only when confident; otherwise the item stays unfiled and the UI
shows the suggestions. A proposed new name becomes a real (AI) category once a *second* similar item
proposes it - so categories emerge from patterns rather than one-offs.
"""

import json
from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sqlalchemy.orm import Session

from app.config import get_settings
from app.embeddings import clip_text, embed_text
from app.models import Category, Document, ImageVector

PALETTE = ["#2f6b45", "#b4452c", "#3d4f86", "#8a7a4f", "#e8825f", "#6b4f86", "#2f6b6b", "#a8432e"]
LEARNED_MIN_PROB = 0.6
ZERO_SHOT_MIN_PROB = 0.5


@dataclass
class Decision:
    category_id: str | None
    confidence: float
    method: str
    suggestions: list[dict] = field(default_factory=list)
    pending_name: str = ""


# --------------------------------------------------------------- signals ----

def _training_set(db: Session, user_id: str) -> tuple[np.ndarray, list[str]]:
    rows = (
        db.query(ImageVector.embedding, Document.category_id)
        .join(Document, Document.id == ImageVector.document_id)
        .filter(Document.user_id == user_id, Document.category_confirmed.is_(True), Document.category_id.isnot(None))
        .all()
    )
    if not rows:
        return np.zeros((0, 0), dtype="float32"), []
    return np.vstack([np.frombuffer(e, dtype="float32") for e, _ in rows]), [c for _, c in rows]


def learned_probs(db: Session, user_id: str, vec: np.ndarray) -> dict[str, float]:
    X, y = _training_set(db, user_id)
    if not y:
        return {}
    keep = {c for c in set(y) if y.count(c) >= get_settings().classifier_min_examples}
    if len(keep) < 2:
        return {}
    mask = [c in keep for c in y]
    clf = LogisticRegression(max_iter=1000, C=2.0)
    clf.fit(X[mask], [c for c, m in zip(y, mask) if m])
    return dict(zip(map(str, clf.classes_), map(float, clf.predict_proba(vec.reshape(1, -1))[0])))


def zero_shot_probs(categories: list[Category], vec: np.ndarray) -> dict[str, float]:
    if not categories:
        return {}
    prompts = clip_text([f"a photo of {c.name.lower()}" + (f": {c.description}" if c.description else "") for c in categories])
    logits = (prompts @ vec.reshape(-1)) * 100  # CLIP logit scale
    probs = np.exp(logits - logits.max())
    probs /= probs.sum()
    return {c.id: float(p) for c, p in zip(categories, probs)}


# Back-compat helpers used by tests / callers
@dataclass
class Assignment:
    category_id: str | None
    confidence: float
    method: str


def learned(db: Session, user_id: str, vec: np.ndarray) -> Assignment | None:
    probs = learned_probs(db, user_id, vec)
    if not probs:
        return None
    best = max(probs, key=probs.get)
    return Assignment(best, probs[best], "classifier")


# -------------------------------------------------------------- decision ----

def _match(categories: list[Category], name: str | None) -> Category | None:
    if not name:
        return None
    n = name.strip().lower()
    return next((c for c in categories if c.name.lower() == n), None)


def decide(db: Session, user_id: str, vec: np.ndarray, claude_name: str | None) -> Decision:
    cats = db.query(Category).filter_by(user_id=user_id).order_by(Category.created_at).all()
    by_id = {c.id: c for c in cats}
    learned_p = learned_probs(db, user_id, vec)
    zero_p = {} if learned_p else zero_shot_probs(cats, vec)
    claude_cat = _match(cats, claude_name)

    scores: dict[str, tuple[float, str]] = {}
    for cid, p in zero_p.items():
        scores[cid] = (p, "zero-shot")
    for cid, p in learned_p.items():
        scores[cid] = (p, "classifier")
    if claude_cat:
        prev = scores.get(claude_cat.id, (0.0, ""))[0]
        scores[claude_cat.id] = (max(prev, 0.75), "claude")

    ranked = sorted(scores.items(), key=lambda kv: kv[1][0], reverse=True)
    suggestions = [
        {"category_id": cid, "name": by_id[cid].name, "score": round(sc, 3), "source": src}
        for cid, (sc, src) in ranked[:3]
        if cid in by_id and sc >= 0.05
    ]
    pending = claude_name.strip()[:40] if claude_name and not claude_cat else ""
    if pending:
        suggestions.insert(0, {"category_id": None, "name": pending, "score": 0.7, "source": "claude-new"})

    best_learned = max(learned_p.items(), key=lambda kv: kv[1], default=(None, 0.0))
    if best_learned[1] >= LEARNED_MIN_PROB:
        return Decision(best_learned[0], best_learned[1], "classifier", suggestions, pending)
    if claude_cat:
        return Decision(claude_cat.id, 0.75, "claude", suggestions, pending)
    best_zero = max(zero_p.items(), key=lambda kv: kv[1], default=(None, 0.0))
    if not claude_name and best_zero[1] >= ZERO_SHOT_MIN_PROB:
        return Decision(best_zero[0], best_zero[1], "zero-shot", suggestions, pending)
    return Decision(None, 0.0, "", suggestions, pending)


def get_or_create(db: Session, user_id: str, name: str, source: str = "ai", description: str = "") -> Category:
    name = " ".join(name.split())[:40] or "Unsorted"
    cats = db.query(Category).filter_by(user_id=user_id).all()
    if found := _match(cats, name):
        return found
    cat = Category(user_id=user_id, name=name, description=description, color=PALETTE[len(cats) % len(PALETTE)], source=source)
    db.add(cat)
    db.flush()
    return cat


def apply(db: Session, doc: Document, d: Decision) -> None:
    doc.category_id, doc.category_confidence, doc.category_method = d.category_id, d.confidence, d.method
    doc.suggestions = json.dumps(d.suggestions)
    doc.pending_category = "" if d.category_id else d.pending_name
    if doc.pending_category:
        group_pending(db, doc)


def group_pending(db: Session, doc: Document) -> Category | None:
    """If another unfiled item proposed the same (or a near-identical) new category, create it for both."""
    others = (
        db.query(Document)
        .filter(Document.user_id == doc.user_id, Document.id != doc.id, Document.category_id.is_(None),
                Document.pending_category != "")
        .all()
    )
    if not others:
        return None
    names = [doc.pending_category] + [o.pending_category for o in others]
    vecs = embed_text([n.lower() for n in names])
    sims = vecs[1:] @ vecs[0]
    matches = [o for o, s, n in zip(others, sims, names[1:])
               if n.lower() == doc.pending_category.lower() or s >= get_settings().group_name_similarity]
    if not matches:
        return None
    first = min(matches, key=lambda d: d.created_at)  # name the group as it was first proposed
    cat = get_or_create(db, doc.user_id, first.pending_category, source="ai")
    for d in [doc, *matches]:
        d.category_id, d.category_method, d.category_confidence, d.pending_category = cat.id, "ai-group", 0.7, ""
    return cat


# ---------------------------------------------------------- suggestions ----

def proposed_groups(db: Session, user_id: str) -> list[dict]:
    """Unfiled items grouped by the new category Claude proposed for them."""
    docs = (
        db.query(Document)
        .filter(Document.user_id == user_id, Document.category_id.is_(None), Document.pending_category != "")
        .order_by(Document.created_at.desc())
        .all()
    )
    groups: dict[str, dict] = {}
    for d in docs:
        g = groups.setdefault(d.pending_category.lower(), {"name": d.pending_category, "documents": []})
        g["documents"].append(d)
    return sorted(groups.values(), key=lambda g: len(g["documents"]), reverse=True)


def _centroids(db: Session, user_id: str) -> dict[str, np.ndarray]:
    rows = (
        db.query(Document.category_id, ImageVector.embedding)
        .join(ImageVector, ImageVector.document_id == Document.id)
        .filter(Document.user_id == user_id, Document.category_id.isnot(None))
        .all()
    )
    groups: dict[str, list[np.ndarray]] = {}
    for cid, emb in rows:
        groups.setdefault(cid, []).append(np.frombuffer(emb, dtype="float32"))
    out = {}
    for cid, vs in groups.items():
        if len(vs) >= 2:
            c = np.mean(vs, axis=0)
            out[cid] = c / max(np.linalg.norm(c), 1e-12)
    return out


def merge_suggestions(db: Session, user_id: str) -> list[dict]:
    """Pairs of categories that look like duplicates: similar names (SBERT) or similar photos (CLIP centroids)."""
    cats = db.query(Category).filter_by(user_id=user_id).order_by(Category.created_at).all()
    if len(cats) < 2:
        return []
    s = get_settings()
    name_vecs = embed_text([c.name.lower() for c in cats])
    cents = _centroids(db, user_id)
    out = []
    for (i, a), (j, b) in combinations(enumerate(cats), 2):
        name_sim = float(name_vecs[i] @ name_vecs[j])
        cent_sim = float(cents[a.id] @ cents[b.id]) if a.id in cents and b.id in cents else 0.0
        if name_sim >= s.group_name_similarity:
            reason, score = "Similar names", name_sim
        elif cent_sim >= s.merge_centroid_similarity:
            reason, score = "Similar photos", cent_sim
        else:
            continue
        # Merge the newer / AI one into the older / user one.
        src, dst = (b, a) if (b.source == "ai" or a.source != "ai") else (a, b)
        out.append({"source": src, "target": dst, "reason": reason, "score": round(score, 3)})
    return sorted(out, key=lambda m: m["score"], reverse=True)
