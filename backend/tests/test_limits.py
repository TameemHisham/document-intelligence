from types import SimpleNamespace

import pytest

from app import usage
from tests.conftest import login, png_bytes

WARRANTY = "CERTIFICATE OF WARRANTY. Dyson Pure Cool TP07. Guaranteed for 2 years."


def boom(*a, **k):
    raise AssertionError("Claude must not be called")


@pytest.fixture()
def no_network(monkeypatch):
    """Pretend a key is set, but make any real Claude request fail the test."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test")
    import anthropic

    monkeypatch.setattr(anthropic.resources.messages.Messages, "parse", boom)
    monkeypatch.setattr(anthropic.resources.beta.messages.Messages, "create", boom)


def set_(monkeypatch, **kw):
    from app.config import get_settings

    for k, v in kw.items():
        monkeypatch.setattr(get_settings(), k, v)


def upload(client, h, monkeypatch, text=WARRANTY, name="w.png"):
    monkeypatch.setattr("app.ingest.extract_text", lambda data, mime: text)
    r = client.post("/documents", headers=h, files={"files": (name, png_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    return r.json()[0]["id"]


def test_cost_math():
    u = SimpleNamespace(input_tokens=1_000_000, output_tokens=100_000)
    assert usage.claude_cost("claude-opus-5-5", u) == pytest.approx(4.0 + 2.0)
    assert usage.claude_cost("claude-haiku-5-5", u) == pytest.approx(0.10 + 0.05)
    assert usage.claude_cost("some-new-model", u) == pytest.approx(10.0 + 5.0)  # unknown: priced high


def test_monthly_budget_blocks_claude_before_any_call(client, monkeypatch, no_network):
    set_(monkeypatch, monthly_budget_usd=0.0)
    h = login(client)
    wid = upload(client, h, monkeypatch)
    doc = client.get(f"/documents/{wid}", headers=h).json()
    assert doc["status"] == "ready"  # still indexed without AI
    assert "budget" in doc["error"].lower()

    r = client.post("/ask", json={"question": "warranty", "document_ids": [wid]}, headers=h)
    assert r.status_code == 429 and "budget" in r.json()["detail"].lower()


def test_user_daily_budget(client, monkeypatch, no_network):
    from app.db import SessionLocal

    h = login(client)
    db = SessionLocal()
    uid = client.get("/auth/me", headers=h).json()["id"]
    usage.record_claude(db, uid, "ask", "claude-opus-5-5", SimpleNamespace(input_tokens=300_000, output_tokens=0))
    db.close()  # $1.20 spent today > $1 default

    wid = upload(client, h, monkeypatch)  # describe must be skipped, not called
    assert client.get(f"/documents/{wid}", headers=h).json()["status"] == "ready"
    r = client.post("/ask", json={"question": "warranty", "document_ids": [wid]}, headers=h)
    assert r.status_code == 429 and "daily" in r.json()["detail"].lower()


def test_ocr_monthly_cap(client, monkeypatch):
    set_(monkeypatch, ocr_backend="vision", ocr_monthly_limit=1)
    calls = []
    monkeypatch.setattr("app.ingest.extract_text", lambda data, mime: calls.append(1) or "text")
    h = login(client)
    for i in range(2):
        r = client.post("/documents", headers=h, files={"files": (f"{i}.png", png_bytes(), "image/png")})
        assert r.status_code == 200
    assert len(calls) == 1  # second image skipped OCR
    docs = client.get("/documents", headers=h).json()
    assert any("OCR limit" in d["error"] for d in docs)
    assert client.get("/usage", headers=h).json()["ocr_images_this_month"] == 1


def test_rejects_fake_images_and_too_many_files(client, monkeypatch):
    h = login(client)
    r = client.post("/documents", headers=h, files={"files": ("x.png", b"not an image", "image/png")})
    assert r.status_code == 415
    set_(monkeypatch, max_files_per_request=2)
    files = [("files", (f"{i}.png", png_bytes(), "image/png")) for i in range(3)]
    assert client.post("/documents", headers=h, files=files).status_code == 400


def test_upload_size_and_daily_limits(client, monkeypatch):
    h = login(client)
    set_(monkeypatch, max_upload_mb=0)
    assert client.post("/documents", headers=h, files={"files": ("a.png", png_bytes(), "image/png")}).status_code == 413
    set_(monkeypatch, max_upload_mb=20, max_uploads_per_day=1)
    upload(client, h, monkeypatch)
    r = client.post("/documents", headers=h, files={"files": ("b.png", png_bytes(), "image/png")})
    assert r.status_code == 429


def test_ask_rate_limit(client, monkeypatch):
    set_(monkeypatch, rate_ask_per_minute=2)
    h = login(client)
    wid = upload(client, h, monkeypatch)
    body = {"question": "warranty", "document_ids": [wid]}
    assert client.post("/ask", json=body, headers=h).status_code == 200
    assert client.post("/ask", json=body, headers=h).status_code == 200
    r = client.post("/ask", json=body, headers=h)
    assert r.status_code == 429 and "Retry-After" in r.headers
