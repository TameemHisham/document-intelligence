"""Spend tracking and hard budget caps for paid APIs (Claude, Google Vision).

Every paid call is checked *before* it's made and recorded *after* with real token counts.
Caps: global monthly USD budget, per-user daily USD budget, monthly OCR image count.
"""

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ApiUsage, User

# USD per 1M tokens (input, output). Unknown models are priced at the most expensive tier.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    # Gemini (query parsing). Thinking tokens are billed as output.
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
}
UNKNOWN_MODEL_PRICE = (10.00, 50.00)
VISION_USD_PER_IMAGE = 0.0015  # after Google's 1,000 free units/month


class LimitExceeded(Exception):
    """A budget or quota would be exceeded; maps to HTTP 429."""


def _month_start() -> datetime:
    return datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _day_start() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def spent_usd(db: Session, since: datetime, user_id: str | None = None) -> float:
    q = db.query(func.coalesce(func.sum(ApiUsage.cost_usd), 0.0)).filter(ApiUsage.created_at >= since)
    if user_id:
        q = q.filter(ApiUsage.user_id == user_id)
    return float(q.scalar())


def count_calls(db: Session, since: datetime, kind: str) -> int:
    return db.query(func.count(ApiUsage.id)).filter(ApiUsage.created_at >= since, ApiUsage.kind == kind).scalar()


def check_ai(db: Session, user_id: str) -> None:
    """Budget gate for any paid LLM call (Claude or Gemini)."""
    check_claude(db, user_id)


def _is_guest(db: Session, user_id: str) -> bool:
    u = db.get(User, user_id)
    return bool(u and u.is_guest)


def check_claude(db: Session, user_id: str, kind: str = "") -> None:
    s = get_settings()
    if _is_guest(db, user_id):
        demo = float(db.query(func.coalesce(func.sum(ApiUsage.cost_usd), 0.0))
                     .filter(ApiUsage.created_at >= _month_start(), ApiUsage.guest.is_(True)).scalar())
        if demo >= s.demo_monthly_budget_usd:
            raise LimitExceeded("The demo's AI allowance for this month is used up - search and browsing still work.")
        if kind == "ask":
            asked = db.query(func.count(ApiUsage.id)).filter(ApiUsage.user_id == user_id, ApiUsage.kind == "ask").scalar()
            if asked >= s.demo_guest_questions:
                raise LimitExceeded(f"Demo limit reached: {s.demo_guest_questions} questions per sandbox. "
                                    "Clone the repo to run your own copy.")
    month = spent_usd(db, _month_start())
    if month >= s.monthly_budget_usd:
        raise LimitExceeded(
            f"Monthly AI budget reached (${month:.2f} of ${s.monthly_budget_usd:.2f}). "
            "Raise MONTHLY_BUDGET_USD to continue."
        )
    today = spent_usd(db, _day_start(), user_id)
    if today >= s.user_daily_budget_usd:
        raise LimitExceeded(f"Daily AI limit reached (${today:.2f} of ${s.user_daily_budget_usd:.2f}). Try again tomorrow.")


def claude_cost(model: str, usage) -> float:
    pin, pout = PRICES.get(model, UNKNOWN_MODEL_PRICE)
    g = lambda name: getattr(usage, name, 0) or 0  # noqa: E731
    input_equiv = g("input_tokens") + 1.25 * g("cache_creation_input_tokens") + 0.1 * g("cache_read_input_tokens")
    return (input_equiv * pin + g("output_tokens") * pout) / 1_000_000


def record_claude(db: Session, user_id: str, kind: str, model: str, usage) -> float:
    cost = claude_cost(model, usage)
    db.add(ApiUsage(
        user_id=user_id, kind=kind, model=model, guest=_is_guest(db, user_id),
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cost_usd=cost,
    ))
    db.commit()
    return cost


def record_gemini(db: Session, user_id: str, model: str, meta) -> float:
    g = lambda name: getattr(meta, name, 0) or 0  # noqa: E731
    u = type("U", (), {"input_tokens": g("prompt_token_count"), "output_tokens": g("candidates_token_count") + g("thoughts_token_count")})
    return record_claude(db, user_id, "parse", model, u)


def check_ocr(db: Session) -> None:
    limit = get_settings().ocr_monthly_limit
    if count_calls(db, _month_start(), "ocr") >= limit:
        raise LimitExceeded(f"Monthly OCR limit reached ({limit} images). Raise OCR_MONTHLY_LIMIT to continue.")


def record_ocr(db: Session, user_id: str) -> None:
    # Counted at list price even inside the free tier, so the budget stays conservative.
    db.add(ApiUsage(user_id=user_id, kind="ocr", model="google-vision", cost_usd=VISION_USD_PER_IMAGE,
                    guest=_is_guest(db, user_id)))
    db.commit()


def summary(db: Session, user_id: str) -> dict:
    s = get_settings()
    return {
        "month_spent_usd": round(spent_usd(db, _month_start()), 4),
        "monthly_budget_usd": s.monthly_budget_usd,
        "today_spent_usd": round(spent_usd(db, _day_start(), user_id), 4),
        "user_daily_budget_usd": s.user_daily_budget_usd,
        "ocr_images_this_month": count_calls(db, _month_start(), "ocr"),
        "ocr_monthly_limit": s.ocr_monthly_limit,
        "claude_model": s.claude_model,
    }
