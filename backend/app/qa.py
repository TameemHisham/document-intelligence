"""Scoped RAG Q&A: retrieve chunks only from the chosen documents (one doc or a project),
add the NER fields, and have Claude answer with [n] citations."""

import logging
import re
from dataclasses import dataclass, field

import anthropic
from sqlalchemy.orm import Session

from app import usage
from app.config import get_settings
from app.describe import client as claude_client
from app.embeddings import embed_text
from app.models import Chunk, Document
from app.ner import Field, summarize_fields
from app import vectors

log = logging.getLogger(__name__)

SYSTEM = """You answer questions about the user's personal photos and documents.

Use only the numbered sources provided. Cite every claim with its source number in square brackets, like [2].
Sources include OCR text (may contain recognition errors), visual descriptions of photos, and extracted fields.
If the sources don't contain the answer, say so plainly and suggest what document might help.
When asked to find or filter items, list the matching items with a one-line reason each.
Today's date is {today}; use it for questions like "is this still valid?". Be concise."""


class AIUnavailable(Exception):
    """Claude couldn't be reached or rejected the request; maps to HTTP 503."""


@dataclass
class Source:
    n: int
    document_id: str
    title: str
    text: str


@dataclass
class Answer:
    text: str
    sources: list[Source] = field(default_factory=list)


def _retrieve(db: Session, user_id: str, question: str, docs: list[Document], k: int = 8) -> list[Source]:
    by_id = {d.id: d for d in docs}
    chunk_rows = db.query(Chunk.id, Chunk.document_id, Chunk.text).filter(Chunk.document_id.in_(by_id)).all()
    chunk_map = {cid: (did, text) for cid, did, text in chunk_rows}
    hits = vectors.search_chunks_subset(db, user_id, embed_text([question])[0], list(chunk_map), k)

    # Always include each scoped document's header chunk when the scope is small,
    # so "which of these…" questions see every item.
    picked: list[int] = [cid for cid, _ in hits]
    if len(docs) <= 15:
        headers = db.query(Chunk.id).filter(Chunk.document_id.in_(by_id), Chunk.idx == 0)
        picked = [cid for (cid,) in headers if cid not in picked] + picked

    sources = []
    for cid in picked:
        did, text = chunk_map[cid]
        sources.append(Source(len(sources) + 1, did, by_id[did].title or by_id[did].filename, text))
    return sources


def _fields_block(docs: list[Document]) -> str:
    lines = []
    for d in docs:
        rows = summarize_fields([Field(e.field, e.label, e.text, e.value) for e in d.entities])
        if rows:
            lines.append(f"- {d.title or d.filename}: " + "; ".join(f"{r['label']}={r['value']}" for r in rows))
    return "\n".join(lines)


def answer(db: Session, user_id: str, question: str, docs: list[Document], history: list[dict]) -> Answer:
    from datetime import date

    sources = _retrieve(db, user_id, question, docs)
    if not sources:
        return Answer("I don't have any processed content in this scope yet.")

    source_text = "\n\n".join(f"[{s.n}] ({s.title})\n{s.text}" for s in sources)
    fields = _fields_block(docs)
    user_msg = f"<sources>\n{source_text}\n</sources>\n"
    if fields:
        user_msg += f"\n<extracted_fields>\n{fields}\n</extracted_fields>\n"
    user_msg += f"\nQuestion: {question}"

    client = claude_client()
    if client is None:  # offline fallback so the pipeline is debuggable without a key
        s = sources[0]
        return Answer(f"(No ANTHROPIC_API_KEY set - showing the best matching passage.) {s.text} [1]", [s])
    usage.check_claude(db, user_id)

    # Bounded history: last 6 turns, each truncated, so follow-ups can't grow the prompt without limit.
    messages = [
        {"role": m["role"], "content": str(m["content"])[:2000]}
        for m in history[-6:]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    if messages and messages[0]["role"] != "user":
        messages = messages[1:]
    messages.append({"role": "user", "content": user_msg})
    try:
        resp = client.beta.messages.create(
            model=get_settings().claude_model,
            max_tokens=get_settings().ask_max_tokens,
            system=SYSTEM.format(today=date.today().isoformat()),
            messages=messages,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},  # grounded lookup; keeps thinking (billed as output) small
        )
    except anthropic.AuthenticationError as e:
        raise AIUnavailable("The Claude API key is invalid. Check ANTHROPIC_API_KEY.") from e
    except anthropic.RateLimitError as e:
        raise AIUnavailable("Claude is rate-limited right now. Wait a minute and try again.") from e
    except anthropic.BadRequestError as e:
        log.warning("qa bad request: %s", e)
        raise AIUnavailable("Claude rejected the request (it may be too large or your credit may be exhausted).") from e
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
        raise AIUnavailable("Couldn't reach Claude. Check your connection and try again.") from e
    except anthropic.APIStatusError as e:
        log.warning("qa failed: %s", e)
        raise AIUnavailable(f"Claude returned an error ({e.status_code}). Try again shortly.") from e
    usage.record_claude(db, user_id, "ask", resp.model, resp.usage)
    if resp.stop_reason == "refusal":
        return Answer("I can't answer that one.")

    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if resp.stop_reason == "max_tokens":
        text += "\n\n(Answer cut off at the length limit.)"
    used = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
    return Answer(text, [s for s in sources if s.n in used])
