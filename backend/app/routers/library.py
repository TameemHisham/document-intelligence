"""Categories, projects, search and ask."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import classifier, qa, query_parser, usage
from app.auth import current_user
from app.db import get_db
from app.models import Category, Document, Project, User
from app.ratelimit import limit
from app.routers.documents import file_into, owned_category
from app.schemas import (
    AskIn, AskOut, CategoryCreateIn, CategoryIn, CategoryOut, CategorySuggestionsOut, FiltersOut, MergeIn,
    MergeSuggestionOut, ProjectDocsIn, ProjectIn, ProjectOut, ProposedOut, SearchHitOut, SearchOut, SourceOut,
    cat_out, doc_out, file_url,
)
from app.search import doc_date
from app.search import search as run_search

router = APIRouter(tags=["library"])
COVERS = 4


# ---- categories -----------------------------------------------------------

def _covers(db: Session, user_id: str) -> dict[str, list[str]]:
    rows = (
        db.query(Document)
        .filter(Document.user_id == user_id, Document.category_id.isnot(None), Document.mime.like("image/%"),
                Document.status == "ready")
        .order_by(doc_date().desc())
        .limit(2000)
        .all()
    )
    out: dict[str, list[str]] = {}
    for d in rows:
        lst = out.setdefault(d.category_id, [])
        if len(lst) < COVERS:
            lst.append(file_url(d))
    return out


def _cat_list(db: Session, user_id: str) -> list[CategoryOut]:
    counts = dict(
        db.query(Document.category_id, func.count()).filter(Document.user_id == user_id).group_by(Document.category_id)
    )
    covers = _covers(db, user_id)
    cats = db.query(Category).filter_by(user_id=user_id).order_by(Category.created_at).all()
    return [cat_out(c, counts.get(c.id, 0), covers.get(c.id)) for c in cats]


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _cat_list(db, user.id)


@router.post("/categories", response_model=CategoryOut)
def create_category(body: CategoryCreateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cat = Category(user_id=user.id, name=" ".join(body.name.split()), description=body.description.strip(),
                   color=body.color, source="user")
    db.add(cat)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"A category named “{body.name}” already exists.")
    if body.document_ids:
        for d in db.query(Document).filter(Document.id.in_(body.document_ids), Document.user_id == user.id):
            file_into(d, cat)
    db.commit()
    return cat_out(cat, len(body.document_ids))


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(category_id: str, body: CategoryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cat = owned_category(db, user, category_id)
    cat.name, cat.description, cat.color = " ".join(body.name.split()), body.description.strip(), body.color
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"A category named “{body.name}” already exists.")
    return cat_out(cat)


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cat = owned_category(db, user, category_id)
    db.query(Document).filter_by(category_id=cat.id).update({"category_id": None, "category_confirmed": False})
    db.delete(cat)
    db.commit()


@router.post("/categories/{category_id}/merge", response_model=CategoryOut)
def merge_category(category_id: str, body: MergeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    src, dst = owned_category(db, user, category_id), owned_category(db, user, body.into_id)
    if src.id == dst.id:
        raise HTTPException(400, "Can't merge a category into itself.")
    db.query(Document).filter_by(category_id=src.id).update({"category_id": dst.id})
    db.delete(src)
    db.commit()
    return next(c for c in _cat_list(db, user.id) if c.id == dst.id)


@router.get("/categories/suggestions", response_model=CategorySuggestionsOut)
def category_suggestions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Merge candidates (similar categories) + AI-proposed new categories for unfiled items."""
    counts = {c.id: c for c in _cat_list(db, user.id)}
    merges = [
        MergeSuggestionOut(source=counts[m["source"].id], target=counts[m["target"].id], reason=m["reason"], score=m["score"])
        for m in classifier.merge_suggestions(db, user.id)
    ]
    proposed = [ProposedOut(name=g["name"], documents=[doc_out(d) for d in g["documents"]])
                for g in classifier.proposed_groups(db, user.id)]
    unfiled = db.query(func.count(Document.id)).filter(
        Document.user_id == user.id, Document.category_id.is_(None), Document.status == "ready").scalar()
    return CategorySuggestionsOut(merges=merges, proposed=proposed, unfiled=unfiled)


# ---- projects -------------------------------------------------------------

def _project(db: Session, user: User, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(404, "project not found")
    return p


def _project_out(p: Project, with_docs: bool = False) -> ProjectOut:
    return ProjectOut(
        id=p.id, name=p.name, created_at=p.created_at, document_count=len(p.documents),
        documents=[doc_out(d) for d in p.documents] if with_docs else [],
    )


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_project_out(p) for p in db.query(Project).filter_by(user_id=user.id).order_by(Project.created_at.desc())]


@router.post("/projects", response_model=ProjectOut)
def create_project(body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Project(user_id=user.id, name=body.name.strip())
    db.add(p)
    db.commit()
    return _project_out(p)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _project_out(_project(db, user, project_id), with_docs=True)


@router.post("/projects/{project_id}/documents", response_model=ProjectOut)
def add_to_project(project_id: str, body: ProjectDocsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _project(db, user, project_id)
    docs = db.query(Document).filter(Document.id.in_(body.document_ids), Document.user_id == user.id).all()
    existing = {d.id for d in p.documents}
    p.documents.extend(d for d in docs if d.id not in existing)
    db.commit()
    return _project_out(p, with_docs=True)


@router.delete("/projects/{project_id}/documents/{document_id}", response_model=ProjectOut)
def remove_from_project(project_id: str, document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _project(db, user, project_id)
    p.documents = [d for d in p.documents if d.id != document_id]
    db.commit()
    return _project_out(p, with_docs=True)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_project(db, user, project_id))
    db.commit()


# ---- search & ask ---------------------------------------------------------

def _category_names(db: Session, user_id: str) -> list[str]:
    return [n for (n,) in db.query(Category.name).filter_by(user_id=user_id)]


@router.get("/search", response_model=SearchOut)
def search(
    q: str = Query(min_length=1, max_length=500),
    kind: str | None = None,
    category_id: str | None = None,
    project_id: str | None = None,
    max_results: int = Query(30, le=100, alias="limit"),
    user: User = Depends(limit("search")),
    db: Session = Depends(get_db),
):
    scope = {d.id for d in _project(db, user, project_id).documents} if project_id else None
    filters = query_parser.parse(db, user.id, q, _category_names(db, user.id))
    hits = run_search(db, user.id, q, max_results, kind, category_id, scope, filters)
    return SearchOut(
        results=[SearchHitOut(document=doc_out(h.document), score=h.score, snippet=h.snippet, matched=h.matched) for h in hits],
        filters=FiltersOut(**filters.model_dump()),
    )


@router.post("/ask", response_model=AskOut)
def ask(body: AskIn, user: User = Depends(limit("ask")), db: Session = Depends(get_db)):
    q = db.query(Document).filter(Document.user_id == user.id, Document.status == "ready")
    if body.project_id:
        ids = [d.id for d in _project(db, user, body.project_id).documents]
        q = q.filter(Document.id.in_(ids))
    elif body.document_ids:
        q = q.filter(Document.id.in_(body.document_ids))
    else:  # whole library: narrow with (free, rule-based) filters + search first
        filters = query_parser.parse_rules(body.question)
        hits = run_search(db, user.id, body.question, 15, filters=filters)
        q = q.filter(Document.id.in_([h.document.id for h in hits]))
    docs = q.all()
    if not docs:
        return AskOut(answer="I couldn't find any matching items in your library for that.", sources=[])
    result = qa.answer(db, user.id, body.question, docs, [t.model_dump() for t in body.history])
    return AskOut(answer=result.text, sources=[SourceOut(**s.__dict__) for s in result.sources])


@router.get("/usage")
def get_usage(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return usage.summary(db, user.id)
