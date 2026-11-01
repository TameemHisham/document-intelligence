"""In-memory sliding-window rate limits per user (single-process MVP; use Redis if you scale out)."""

import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException

from app.auth import current_user
from app.config import get_settings
from app.models import User

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def hit(key: str, limit: int, window_s: float = 60.0) -> None:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            retry = int(window_s - (now - q[0])) + 1
            raise HTTPException(429, f"Too many requests. Try again in {retry}s.", headers={"Retry-After": str(retry)})
        q.append(now)


def reset() -> None:
    with _lock:
        _hits.clear()


def limit(action: str):
    """Dependency: `user: User = Depends(limit("ask"))` - authenticates and rate-limits."""

    def dep(user: User = Depends(current_user)) -> User:
        per_minute = getattr(get_settings(), f"rate_{action}_per_minute")
        hit(f"{action}:{user.id}", per_minute)
        return user

    return dep
