from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import current_user, session_token, upsert_user, verify_google_credential
from app.config import get_settings
from app.db import get_db
from app.models import User
from app.schemas import AuthOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleIn(BaseModel):
    credential: str


class DevIn(BaseModel):
    email: str = "dev@example.com"


def _out(user: User) -> AuthOut:
    return AuthOut(token=session_token(user), user=UserOut(id=user.id, email=user.email, name=user.name, picture=user.picture))


@router.post("/google", response_model=AuthOut)
def google_login(body: GoogleIn, db: Session = Depends(get_db)):
    info = verify_google_credential(body.credential)
    user = upsert_user(db, info["sub"], info.get("email", ""), info.get("name", ""), info.get("picture", ""))
    return _out(user)


@router.post("/dev", response_model=AuthOut)
def dev_login(body: DevIn, db: Session = Depends(get_db)):
    if not get_settings().dev_auth:
        raise HTTPException(404)
    user = upsert_user(db, f"dev:{body.email}", body.email, body.email.split("@")[0])
    return _out(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut(id=user.id, email=user.email, name=user.name, picture=user.picture)
