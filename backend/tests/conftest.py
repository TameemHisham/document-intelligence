import io
import os

import pytest

# Run the whole suite against Postgres + pgvector with:
#   TEST_DATABASE_URL=postgresql+psycopg://postgres:pg@localhost:55432/di pytest
os.environ["DI_IGNORE_DOTENV"] = "1"  # never read the developer's backend/.env in tests
PG_URL = os.environ.get("TEST_DATABASE_URL", "")
if PG_URL:
    os.environ["DATABASE_URL"] = PG_URL
    os.environ["VECTOR_BACKEND"] = "pgvector"  # must be set before app.models is imported
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FAKE_MODELS", "true")
    monkeypatch.setenv("OCR_BACKEND", "none")
    monkeypatch.setenv("DEV_AUTH", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    from app import db, ratelimit, storage
    from app.config import get_settings

    ratelimit.reset()
    get_settings.cache_clear()
    storage.get_storage.cache_clear()
    db.reset_engine()
    if PG_URL:
        from sqlalchemy import text

        with db.engine().begin() as conn:  # fresh schema per test
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
    db.reset_engine()


def login(client, email="a@example.com") -> dict:
    r = client.post("/auth/dev", json={"email": email})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def png_bytes(color="white") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buf, format="PNG")
    return buf.getvalue()
