import json
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.auth import file_token
from app.models import Category, Document
from app.ner import Field as NerField
from app.ner import summarize_fields


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    picture: str


class AuthOut(BaseModel):
    token: str
    user: UserOut


class CategoryOut(BaseModel):
    id: str
    name: str
    description: str = ""
    color: str
    source: str
    count: int = 0
    covers: list[str] = []  # image URLs of recent items, for collage thumbnails


class Suggestion(BaseModel):
    category_id: str | None  # None = a new category Claude proposed
    name: str
    score: float
    source: str


class DocumentOut(BaseModel):
    id: str
    filename: str
    mime: str
    kind: str
    status: str
    error: str
    title: str
    summary: str
    caption: str
    category: CategoryOut | None
    category_confidence: float
    category_method: str
    category_confirmed: bool
    suggestions: list[Suggestion]
    favorite: bool
    taken_at: datetime | None
    created_at: datetime
    file_url: str


class DocumentDetail(DocumentOut):
    ocr_text: str
    fields: list[dict]
    project_ids: list[str]


def file_url(d: Document) -> str:
    return f"/documents/{d.id}/file?t={file_token(d.user_id, d.id)}"


def cat_out(c: Category | None, count: int = 0, covers: list[str] | None = None) -> CategoryOut | None:
    if c is None:
        return None
    return CategoryOut(id=c.id, name=c.name, description=c.description or "", color=c.color, source=c.source,
                       count=count, covers=covers or [])


def doc_out(d: Document) -> DocumentOut:
    try:
        sugg = [Suggestion(**s) for s in json.loads(d.suggestions or "[]")]
    except (ValueError, TypeError):
        sugg = []
    return DocumentOut(
        id=d.id, filename=d.filename, mime=d.mime, kind=d.kind, status=d.status, error=d.error,
        title=d.title or d.filename, summary=d.summary, caption=d.caption, category=cat_out(d.category),
        category_confidence=d.category_confidence, category_method=d.category_method,
        category_confirmed=d.category_confirmed, suggestions=sugg, favorite=d.favorite,
        taken_at=d.taken_at, created_at=d.created_at, file_url=file_url(d),
    )


def doc_detail(d: Document) -> DocumentDetail:
    fields = summarize_fields([NerField(e.field, e.label, e.text, e.value) for e in d.entities])
    return DocumentDetail(**doc_out(d).model_dump(), ocr_text=d.ocr_text, fields=fields, project_ids=[p.id for p in d.projects])


class DocumentPatch(BaseModel):
    title: str | None = None
    category_id: str | None = None
    new_category_name: str | None = Field(None, max_length=40)  # accept an AI-proposed category
    favorite: bool | None = None


class BulkIn(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=500)
    action: Literal["categorize", "favorite", "unfavorite", "delete", "accept_suggestions"]
    category_id: str | None = None


class BulkOut(BaseModel):
    updated: int


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    description: str = Field("", max_length=200)
    color: str = Field("#2f6b45", pattern=r"^#[0-9a-fA-F]{6}$")


class CategoryCreateIn(CategoryIn):
    document_ids: list[str] = []  # file these items into the new category


class MergeIn(BaseModel):
    into_id: str


class MergeSuggestionOut(BaseModel):
    source: CategoryOut
    target: CategoryOut
    reason: str
    score: float


class ProposedOut(BaseModel):
    name: str
    documents: list[DocumentOut]


class CategorySuggestionsOut(BaseModel):
    merges: list[MergeSuggestionOut]
    proposed: list[ProposedOut]
    unfiled: int


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ProjectDocsIn(BaseModel):
    document_ids: list[str]


class ProjectOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    document_count: int
    documents: list[DocumentOut] = []


class SearchHitOut(BaseModel):
    document: DocumentOut
    score: float
    snippet: str
    matched: list[str]


class FiltersOut(BaseModel):
    semantic_query: str
    date_from: date | None
    date_to: date | None
    kind: str | None
    category: str | None
    min_amount: float | None
    max_amount: float | None
    parsed_by: str


class SearchOut(BaseModel):
    results: list[SearchHitOut]
    filters: FiltersOut


class ChatTurn(BaseModel):
    role: str
    content: str


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] | None = None
    project_id: str | None = None
    history: list[ChatTurn] = []


class SourceOut(BaseModel):
    n: int
    document_id: str
    title: str
    text: str


class AskOut(BaseModel):
    answer: str
    sources: list[SourceOut]
