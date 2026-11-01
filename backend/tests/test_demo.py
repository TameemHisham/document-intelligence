from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import usage
from tests.conftest import login, png_bytes

WARRANTY = "CERTIFICATE OF WARRANTY. AeroBreeze AB-7. Purchase date: 14 November 2024. Guaranteed for 2 years from the date of purchase."


@pytest.fixture()
def demo(client, monkeypatch):
    from app.config import get_settings

    s = get_settings()
    for k, v in dict(demo_enabled=True, owner_emails="owner@example.com", demo_guest_questions=2, demo_guest_uploads=1).items():
        monkeypatch.setattr(s, k, v)
    monkeypatch.setattr("app.ingest.extract_text", lambda data, mime: WARRANTY)
    return client


def template_token(client):
    owner = login(client, "owner@example.com")
    r = client.post("/auth/demo-template", headers=owner)
    assert r.status_code == 200 and r.json()["user"]["is_template"]
    return {"Authorization": f"Bearer {r.json()['token']}"}


def guest(client):
    r = client.post("/auth/guest")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["is_guest"]
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_guest_gets_private_copy_of_template(demo):
    t = template_token(demo)
    doc = demo.post("/documents", headers=t, files={"files": ("w.png", png_bytes(), "image/png")}).json()[0]
    pid = demo.post("/projects", json={"name": "Appliances"}, headers=t).json()["id"]
    demo.post(f"/projects/{pid}/documents", json={"document_ids": [doc["id"]]}, headers=t)

    g1, g2 = guest(demo), guest(demo)
    docs = demo.get("/documents", headers=g1).json()
    assert len(docs) == 1 and docs[0]["id"] != doc["id"]
    assert demo.get("/projects", headers=g1).json()[0]["document_count"] == 1
    assert demo.get("/search", params={"q": "warranty guaranteed"}, headers=g1).json()["results"]  # vectors cloned
    detail = demo.get(f"/documents/{docs[0]['id']}", headers=g1).json()
    assert {"field": "expiry_date", "label": "Expires", "value": "2026-11-14"} in detail["fields"]
    assert demo.get(detail["file_url"]).status_code == 200  # shared file served

    # guest deletes their copy: template file and the other guest's copy survive
    demo.delete(f"/documents/{docs[0]['id']}", headers=g1)
    other = demo.get("/documents", headers=g2).json()[0]
    assert demo.get(demo.get(f"/documents/{other['id']}", headers=g2).json()["file_url"]).status_code == 200
    assert demo.get("/documents", headers=t).json()[0]["id"] == doc["id"]


def test_guest_limits(demo, monkeypatch):
    t = template_token(demo)
    doc_id = demo.post("/documents", headers=t, files={"files": ("w.png", png_bytes(), "image/png")}).json()[0]["id"]
    g = guest(demo)
    gid = demo.get("/documents", headers=g).json()[0]["id"]

    # uploads: 1 allowed
    assert demo.post("/documents", headers=g, files={"files": ("a.png", png_bytes(), "image/png")}).status_code == 200
    r = demo.post("/documents", headers=g, files={"files": ("b.png", png_bytes(), "image/png")})
    assert r.status_code == 429 and "Demo limit" in r.json()["detail"]

    # questions: counted per guest; pretend Claude answered twice already
    from app.config import get_settings
    from app.db import SessionLocal

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test")
    db = SessionLocal()
    uid = demo.get("/auth/me", headers=g).json()["id"]
    for _ in range(2):
        usage.record_claude(db, uid, "ask", "claude-sonnet-5-5", SimpleNamespace(input_tokens=10, output_tokens=10))
    db.close()
    r = demo.post("/ask", json={"question": "warranty", "document_ids": [gid]}, headers=g)
    assert r.status_code == 429 and "questions per sandbox" in r.json()["detail"]
    assert demo.get("/usage", headers=g).json()["demo"]["questions_left"] == 0
    assert doc_id


def test_demo_budget_shared_by_guests(demo, monkeypatch):
    from app.config import get_settings
    from app.db import SessionLocal

    template_token(demo)
    g = guest(demo)
    uid = demo.get("/auth/me", headers=g).json()["id"]
    db = SessionLocal()
    usage.record_claude(db, uid, "describe", "claude-sonnet-5-5", SimpleNamespace(input_tokens=1_000_000, output_tokens=0))  # $2
    with pytest.raises(usage.LimitExceeded, match="demo's AI allowance"):
        usage.check_claude(db, guest_id := demo.get("/auth/me", headers=guest(demo)).json()["id"])
    usage.check_claude(db, demo.get("/auth/me", headers=login(demo, "owner@example.com")).json()["id"])  # owner unaffected
    db.close()
    assert guest_id


def test_expired_guest_is_rejected_and_purged(demo):
    from app.db import SessionLocal
    from app.models import User

    template_token(demo)
    g = guest(demo)
    db = SessionLocal()
    u = db.query(User).filter_by(is_guest=True).one()
    u.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    db.close()
    r = demo.get("/documents", headers=g)
    assert r.status_code == 401 and "expired" in r.json()["detail"]
    guest(demo)  # creating a new sandbox purges the expired one
    db = SessionLocal()
    assert db.query(User).filter_by(is_guest=True).count() == 1
    db.close()


def test_access_rules(demo, monkeypatch):
    # non-owners can't sign in with Google on a demo deployment
    monkeypatch.setattr("app.routers.auth.verify_google_credential", lambda c: {"sub": "x", "email": "someone@else.com"})
    r = demo.post("/auth/google", json={"credential": "x"})
    assert r.status_code == 403 and "Try the demo" in r.json()["detail"]
    # guests can't open the template; per-IP rate limit on sandboxes
    g = guest(demo)
    assert demo.post("/auth/demo-template", headers=g).status_code == 403
    for _ in range(4):  # 5 sandboxes per IP per hour
        guest(demo)
    assert demo.post("/auth/guest").status_code == 429


def test_demo_disabled_by_default(client):
    assert client.post("/auth/guest").status_code == 404
