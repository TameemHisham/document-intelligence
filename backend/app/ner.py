"""Turn unstructured OCR text into queryable fields: spaCy NER + targeted rules."""

import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from dateutil import parser as dateparser
from dateutil.relativedelta import relativedelta

from app.config import get_settings

LABEL_TO_FIELD = {
    "DATE": "date",
    "MONEY": "money",
    "ORG": "org",
    "PERSON": "person",
    "GPE": "place",
    "LOC": "place",
    "FAC": "place",
    "PRODUCT": "product",
}

EXPIRY_CUES = re.compile(r"expir|valid (until|through|thru|till)|warranty (ends|end date)|use by|best before", re.I)
PURCHASE_CUES = re.compile(r"purchas|date of sale|invoice date|bought|order date", re.I)
TOTAL_CUES = re.compile(r"\b(total|amount due|balance due|grand total)\b", re.I)
SERIAL_RE = re.compile(r"\bserial\s*(?:no\.?|number|#)?\s*[:#]?\s*((?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{4,})", re.I)
CODE_RE = re.compile(r"\b(?=[A-Z0-9-]*\d)(?=[A-Z0-9-]*[A-Z])[A-Z0-9]{2,}(?:-[A-Z0-9]+)+\b")  # e.g. AB7-4821-9930
AMOUNT_RE = re.compile(r"(?:€|\$|£|EUR|USD|GBP)?\s*\d[\d,]*\.\d{2}\b")
DURATION_RE = re.compile(r"(\d+|one|two|three|four|five|ten)[\s-]*(year|month)s?", re.I)
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10}


@dataclass
class Field:
    field: str
    label: str
    text: str
    value: str = ""


@lru_cache
def _nlp():
    import spacy

    return spacy.load(get_settings().spacy_model)


CALENDAR_RE = re.compile(
    r"\b\d{4}\b|\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.I
)


def _parse_date(text: str) -> date | None:
    """Only parse things that look like calendar dates ("2 years" is a DATE entity too)."""
    if not CALENDAR_RE.search(text):
        return None
    try:
        return dateparser.parse(text, dayfirst=True, fuzzy=True, default=None).date()
    except (ValueError, OverflowError, AttributeError, TypeError):
        return None


def _parse_money(text: str) -> str:
    m = re.search(r"\d[\d,]*(?:\.\d{1,2})?", text)
    return m.group(0).replace(",", "") if m else ""


def extract_fields(text: str) -> list[Field]:
    if not text.strip():
        return []
    doc = _nlp()(text[:100_000])
    fields: list[Field] = []
    seen: set[tuple[str, str]] = set()

    def add(f: Field):
        key = (f.field, f.text.lower())
        if key not in seen:
            seen.add(key)
            fields.append(f)

    purchase: date | None = None
    for sent in doc.sents:
        s = sent.text
        for ent in sent.ents:
            field = LABEL_TO_FIELD.get(ent.label_)
            if not field:
                continue
            value = ""
            if field == "date":
                d = _parse_date(ent.text)
                value = d.isoformat() if d else ""
                if d and EXPIRY_CUES.search(s):
                    add(Field("expiry_date", ent.label_, ent.text, value))
                elif d and PURCHASE_CUES.search(s):
                    purchase = purchase or d
                    add(Field("purchase_date", ent.label_, ent.text, value))
            elif field == "money":
                value = _parse_money(ent.text)
            add(Field(field, ent.label_, ent.text, value))

    if total := _find_total(text):
        add(total)

    serials = [m.group(1) for m in SERIAL_RE.finditer(text)]
    if not serials and re.search(r"\bserial\b", text, re.I):
        # OCR often reads label and value columns separately ("Serial no.:" ... "AB7-4821-9930").
        serials = sorted(CODE_RE.findall(text), key=len, reverse=True)[:1]  # longest: skip model names like AB-7
    for sn in serials:
        add(Field("serial", "RULE", sn, sn))

    # Derive expiry from "guaranteed for 2 years from date of purchase".
    if purchase and not any(f.field == "expiry_date" for f in fields) and re.search(r"warrant|guarant", text, re.I):
        m = DURATION_RE.search(text)
        if m:
            n = int(m.group(1)) if m.group(1).isdigit() else WORDNUM[m.group(1).lower()]
            delta = relativedelta(years=n) if m.group(2).lower() == "year" else relativedelta(months=n)
            exp = purchase + delta
            add(Field("expiry_date", "DERIVED", f"{m.group(0)} from {purchase.isoformat()}", exp.isoformat()))
    return fields


def _find_total(text: str) -> Field | None:
    """Amount on the TOTAL line, else on the next line, else the largest amount (receipts list items below the total)."""
    lines = [ln.strip() for ln in text.splitlines()]
    for i, line in enumerate(lines):
        cue = TOTAL_CUES.search(line)
        if not cue:
            continue
        for candidate in (line[cue.end():], lines[i + 1] if i + 1 < len(lines) else ""):
            if m := AMOUNT_RE.search(candidate):
                return Field("total", "RULE", m.group(0).strip(), _parse_money(m.group(0)))
        amounts = [m.group(0).strip() for m in AMOUNT_RE.finditer(text)]
        if amounts:
            best = max(amounts, key=lambda a: float(_parse_money(a)))
            return Field("total", "RULE", best, _parse_money(best))
    return None


FIELD_LABELS = {
    "expiry_date": "Expires",
    "purchase_date": "Purchased",
    "total": "Total",
    "serial": "Serial",
    "org": "Organization",
    "person": "People",
    "place": "Place",
    "product": "Product",
    "date": "Dates",
    "money": "Amounts",
}


def summarize_fields(fields: list[Field]) -> list[dict]:
    """Collapse entity list into display rows: one row per field, values joined."""
    rows: dict[str, list[str]] = {}
    for f in fields:
        shown = f.value if f.field in ("expiry_date", "purchase_date") and f.value else f.text
        vals = rows.setdefault(f.field, [])
        if shown not in vals:
            vals.append(shown)
    return [
        {"field": k, "label": FIELD_LABELS.get(k, k), "value": ", ".join(v[:4])}
        for k in FIELD_LABELS
        if (v := rows.get(k))
    ]
