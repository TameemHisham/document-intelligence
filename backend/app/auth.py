from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Category, User

DEFAULT_CATEGORIES = [
    ("Warranties & Manuals", "#b4452c"),
    ("Study Notes", "#2f6b45"),
    ("Receipts & Bills", "#8a7a4f"),
    ("Family & Trips", "#e8825f"),
    ("Books & Articles", "#3d4f86"),
]

_bearer = HTTPBearer(auto_error=False)


def _encode(payload: dict, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({**payload, "iat": now, "exp": now + ttl}, get_settings().jwt_secret, algorithm="HS256")


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")


def session_token(user: User) -> str:
    return _encode({"sub": user.id, "typ": "session"}, timedelta(hours=get_settings().jwt_ttl_hours))


def file_token(user_id: str, document_id: str) -> str:
    """Short-lived token scoped to one file, so <img src> can load it without the session JWT."""
    return _encode(
        {"sub": user_id, "doc": document_id, "typ": "file"},
        timedelta(minutes=get_settings().file_token_ttl_minutes),
    )


def check_file_token(token: str, document_id: str) -> str:
    claims = _decode(token)
    if claims.get("typ") != "file" or claims.get("doc") != document_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "token not valid for this file")
    return claims["sub"]


def verify_google_credential(credential: str) -> dict:
    from google.auth.transport import requests as g_requests
    from google.oauth2 import id_token

    client_id = get_settings().google_client_id
    if not client_id:
        raise HTTPException(500, "GOOGLE_CLIENT_ID is not configured")
    try:
        return id_token.verify_oauth2_token(credential, g_requests.Request(), client_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid Google credential: {e}")


def upsert_user(db: Session, sub: str, email: str, name: str = "", picture: str = "") -> User:
    user = db.query(User).filter_by(google_sub=sub).one_or_none()
    if user is None:
        user = User(google_sub=sub, email=email, name=name, picture=picture)
        db.add(user)
        db.flush()
        for cname, color in DEFAULT_CATEGORIES:
            db.add(Category(user_id=user.id, name=cname, color=color, source="default"))
    else:
        user.email, user.name, user.picture = email, name or user.name, picture or user.picture
    db.commit()
    return user


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    claims = _decode(creds.credentials)
    if claims.get("typ") != "session":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong token type")
    user = db.get(User, claims["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return user
