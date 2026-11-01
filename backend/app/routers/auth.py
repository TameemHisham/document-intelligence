from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import demo
from app.auth import check_owner, current_user, is_owner, session_token, upsert_user, verify_google_credential
from app.ratelimit import hit
from app.config import get_settings
from app.db import get_db
from app.models import User
from app.schemas import AuthOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleIn(BaseModel):
    credential: str


class DevIn(BaseModel):
    email: str = "dev@example.com"


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, email=user.email, name=user.name, picture=user.picture, is_guest=user.is_guest,
        is_owner=is_owner(user), is_template=user.google_sub == demo.TEMPLATE_SUB, expires_at=user.expires_at,
        demo_enabled=get_settings().demo_enabled,
    )


def _out(user: User) -> AuthOut:
    return AuthOut(token=session_token(user), user=user_out(user))


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")  # Cloud Run sits behind Google's front end
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")


@router.post("/google", response_model=AuthOut)
def google_login(body: GoogleIn, db: Session = Depends(get_db)):
    info = verify_google_credential(body.credential)
    check_owner(info.get("email", ""))
    user = upsert_user(db, info["sub"], info.get("email", ""), info.get("name", ""), info.get("picture", ""))
    return _out(user)


@router.post("/dev", response_model=AuthOut)
def dev_login(body: DevIn, db: Session = Depends(get_db)):
    if not get_settings().dev_auth:
        raise HTTPException(404)
    user = upsert_user(db, f"dev:{body.email}", body.email, body.email.split("@")[0])
    return _out(user)


@router.post("/guest", response_model=AuthOut)
def guest_login(request: Request, db: Session = Depends(get_db)):
    """One click, no account: a private sandbox copied from the demo library."""
    s = get_settings()
    if not s.demo_enabled:
        raise HTTPException(404)
    hit(f"guest-ip:{client_ip(request)}", s.demo_sessions_per_ip_per_hour, 3600)
    demo.purge_expired(db)
    if demo.guests_created_today(db) >= s.demo_sessions_per_day:
        raise HTTPException(429, "The demo is busy today - please try again tomorrow.")
    return _out(demo.create_guest(db))


@router.post("/demo-template", response_model=AuthOut)
def edit_demo_library(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Owner switches into the template account to curate what every guest starts with."""
    if not get_settings().demo_enabled or not is_owner(user):
        raise HTTPException(403, "Only the owner can edit the demo library.")
    return _out(demo.template_user(db))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user_out(user)
