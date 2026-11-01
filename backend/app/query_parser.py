"""Natural-language search -> structured filters + the semantic part to embed.

"receipts over 40 euros from last summer" ->
    semantic_query="receipts", min_amount=40, date_from=2026-06-01, date_to=2026-08-31

Gemini does the translation when configured (cheap Flash-Lite call, budget-gated);
otherwise a small rule parser handles years, months, relative dates, amounts and photo/document words.
"""

import logging
import re
from calendar import monthrange
from datetime import date, timedelta
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import usage
from app.config import get_settings

log = logging.getLogger(__name__)


class QueryFilters(BaseModel):
    semantic_query: str = Field(description="What to search for by meaning, with date/amount/type words removed. Empty if nothing remains.")
    date_from: date | None = Field(None, description="Inclusive start date the item was taken/created")
    date_to: date | None = Field(None, description="Inclusive end date")
    kind: Literal["photo", "document"] | None = Field(None, description="'photo' for pictures/photos, 'document' for receipts, scans, notes, PDFs")
    category: str | None = Field(None, description="One of the user's category names if the query clearly targets it, else null")
    min_amount: float | None = Field(None, description="Minimum money amount, e.g. 'over 40 euros' -> 40")
    max_amount: float | None = Field(None, description="Maximum money amount")
    parsed_by: str = "rules"

    def has_filters(self) -> bool:
        return any(v is not None for v in (self.date_from, self.date_to, self.kind, self.category, self.min_amount, self.max_amount))


# ---------------------------------------------------------------- rules ----

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
SEASONS = {"spring": (3, 5), "summer": (6, 8), "autumn": (9, 11), "fall": (9, 11), "winter": (12, 2)}
PHOTO_WORDS = re.compile(r"\b(photos?|pictures?|pics?|images?|selfies?)\b", re.I)
DOC_WORDS = re.compile(r"\b(documents?|docs?|pdfs?|scans?)\b", re.I)
AMOUNT = r"(?:€|\$|£)?\s*(\d+(?:[.,]\d{1,2})?)\s*(?:€|\$|£|eur(?:os?)?|usd|dollars?|pounds?|gbp)?"
MIN_RE = re.compile(rf"\b(?:over|above|more than|at least|>=?)\s*{AMOUNT}", re.I)
MAX_RE = re.compile(rf"\b(?:under|below|less than|at most|<=?)\s*{AMOUNT}", re.I)


def _month_range(y: int, m: int) -> tuple[date, date]:
    return date(y, m, 1), date(y, m, monthrange(y, m)[1])


def parse_rules(q: str, today: date | None = None) -> QueryFilters:
    today = today or date.today()
    f = QueryFilters(semantic_query=q)
    rest = q

    def cut(m: re.Match) -> None:
        nonlocal rest
        rest = rest.replace(m.group(0), " ")

    if m := MIN_RE.search(rest):
        f.min_amount = float(m.group(1).replace(",", "."))
        cut(m)
    if m := MAX_RE.search(rest):
        f.max_amount = float(m.group(1).replace(",", "."))
        cut(m)

    year_m = re.search(r"\b(?:in|from|during)?\s*(19\d{2}|20\d{2})\b", rest, re.I)
    year = int(year_m.group(1)) if year_m else None
    if m := re.search(r"\b(?:in|from|during)?\s*(last|this)\s+(year|month|week)\b", rest, re.I):
        which, unit = m.group(1).lower(), m.group(2).lower()
        if unit == "year":
            y = today.year - (which == "last")
            f.date_from, f.date_to = date(y, 1, 1), date(y, 12, 31)
        elif unit == "month":
            first = today.replace(day=1)
            if which == "last":
                first = (first - timedelta(days=1)).replace(day=1)
            f.date_from, f.date_to = _month_range(first.year, first.month)
        else:
            start = today - timedelta(days=today.weekday() + (7 if which == "last" else 0))
            f.date_from, f.date_to = start, start + timedelta(days=6)
        cut(m)
    # Needs "in/from/during" or "last/this": in "winter street" the season describes the picture, not a date.
    elif m := re.search(r"\b(?:(?:in|from|during)\s+(?:the\s+)?(?:(last|this)\s+)?|(last|this)\s+)"
                        r"(spring|summer|autumn|fall|winter)\b", rest, re.I):
        which = (m.group(1) or m.group(2) or "").lower()
        a, b = SEASONS[m.group(3).lower()]
        if year:
            y = year
        elif which == "last":
            y = today.year - 1
        elif which == "this":
            y = today.year
        else:  # bare season: the most recent one that has started
            y = today.year if date(today.year, a, 1) <= today else today.year - 1
        f.date_from = date(y, a, 1)
        f.date_to = _month_range(y + (1 if b < a else 0), b)[1]
        cut(m)
        if year_m:
            cut(year_m)
    elif m := re.search(r"\b(?:in|from|during)?\s*(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b\.?", rest, re.I):
        mo = MONTHS[m.group(1).lower()]
        y = year or (today.year if mo <= today.month else today.year - 1)
        f.date_from, f.date_to = _month_range(y, mo)
        cut(m)
        if year_m:
            cut(year_m)
    elif year_m:
        f.date_from, f.date_to = date(year, 1, 1), date(year, 12, 31)
        cut(year_m)

    if m := PHOTO_WORDS.search(rest):
        f.kind = "photo"
        cut(m)
    elif m := DOC_WORDS.search(rest):
        f.kind = "document"
        cut(m)

    rest = re.sub(r"\b(of|from|in|with|my|all|show me|find|the)\b", " ", rest, flags=re.I)
    f.semantic_query = " ".join(rest.split())
    return f


# --------------------------------------------------------------- gemini ----

PROMPT = """Translate a personal photo/document library search into filters.
Today is {today}. The user's categories: {categories}.
Only set a filter when the query clearly asks for it. Put everything else (objects, places, topics) in semantic_query.

Query: {query}"""


@lru_cache
def _gemini():
    from google import genai

    s = get_settings()
    if s.gemini_use_vertex:
        return genai.Client(vertexai=True, project=s.gcp_project or None, location=s.gemini_location)
    return genai.Client(api_key=s.gemini_api_key)


def gemini_enabled() -> bool:
    s = get_settings()
    return bool(s.gemini_api_key or s.gemini_use_vertex)


def parse_gemini(db: Session, user_id: str, q: str, categories: list[str]) -> QueryFilters:
    from google.genai import types

    usage.check_ai(db, user_id)
    s = get_settings()
    resp = _gemini().models.generate_content(
        model=s.gemini_model,
        contents=PROMPT.format(today=date.today().isoformat(), categories=", ".join(categories) or "(none)", query=q),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=QueryFilters,
            max_output_tokens=300,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    usage.record_gemini(db, user_id, s.gemini_model, resp.usage_metadata)
    parsed = resp.parsed
    if not isinstance(parsed, QueryFilters):
        raise ValueError("Gemini returned no structured output")
    parsed.parsed_by = "gemini"
    return parsed


def parse(db: Session, user_id: str, q: str, categories: list[str]) -> QueryFilters:
    if gemini_enabled():
        try:
            f = parse_gemini(db, user_id, q, categories)
            if f.category and f.category.lower() not in {c.lower() for c in categories}:
                f.category = None  # never invent categories
            return f
        except usage.LimitExceeded:
            pass  # over budget: rules are free
        except Exception as e:  # network, model name, quota: search must still work
            log.warning("Gemini query parsing failed, using rules: %s", e)
    return parse_rules(q)
