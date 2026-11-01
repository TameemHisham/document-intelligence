"""One Claude call per upload: title, summary, visual caption, kind, and a category suggestion.

The caption matters for photos with no text ("person in a black hoodie on a mountain ridge"):
it gets embedded with SBERT so visual details become text-searchable alongside CLIP.
"""

import base64
import logging
from types import SimpleNamespace
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app import usage
from app.config import get_settings

log = logging.getLogger(__name__)


class Description(BaseModel):
    title: str = Field(description="Short specific title, max 6 words, e.g. 'Dyson Pure Cool TP07 Warranty'")
    summary: str = Field(description="One sentence with the key facts (who/what/when/amounts)")
    caption: str = Field(description="Literal visual description: objects, people, clothing and colors, setting, scenery")
    kind: Literal["photo", "document"] = Field(description="'document' if it is mainly text (receipt, notes, manual, letter)")
    category: str = Field(
        description="Exact name of the existing category that fits (name only, no description), "
        "or a new 1-3 word category name if none fits"
    )


SYSTEM = (
    "You catalogue items in a personal photo and document library. "
    "Describe exactly what is visible or written; do not guess names of people."
)


def client() -> anthropic.Anthropic | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    return anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=s.claude_timeout_s, max_retries=s.claude_max_retries)


def describe(
    db: Session, user_id: str, image_jpeg: bytes | None, text: str, filename: str, categories: list[str]
) -> Description | None:
    """Returns None when Claude is unavailable; raises usage.LimitExceeded when over budget."""
    c = client()
    if c is None:
        return None
    usage.check_claude(db, user_id)
    content: list[dict] = []
    if image_jpeg:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(image_jpeg).decode()},
        })
    prompt = f"Filename: {filename}\nExisting categories: {', '.join(categories) or '(none)'}\n"
    if text.strip():
        prompt += f"\nExtracted text (OCR, may be noisy):\n<text>\n{text[:6000]}\n</text>\n"
    content.append({"type": "text", "text": prompt + "\nDescribe this item."})
    try:
        resp = c.messages.parse(
            model=get_settings().claude_model,
            max_tokens=get_settings().describe_max_tokens,
            system=SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_format=Description,
            output_config={"effort": "low"},  # simple cataloguing; less thinking = fewer billed tokens
        )
    except anthropic.APIError as e:
        log.warning("describe failed: %s", e)
        return None
    except ValidationError as e:
        # Output didn't parse (e.g. cut off at max_tokens). The call was still billed, so record
        # a worst-case estimate to keep the budget conservative.
        log.warning("describe output invalid for %s: %s", filename, e)
        worst = SimpleNamespace(input_tokens=4000, output_tokens=get_settings().describe_max_tokens)
        usage.record_claude(db, user_id, "describe", get_settings().claude_model, worst)
        return None
    usage.record_claude(db, user_id, "describe", resp.model, resp.usage)
    if resp.stop_reason != "end_turn" or resp.parsed_output is None:  # refusal, max_tokens, …
        log.warning("describe for %s stopped with %s", filename, resp.stop_reason)
        return None
    return resp.parsed_output
