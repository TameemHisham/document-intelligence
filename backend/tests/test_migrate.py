import sqlite3

import pytest

from tests.conftest import PG_URL


@pytest.mark.skipif(bool(PG_URL), reason="sqlite-specific")
def test_adds_missing_columns_to_old_database(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    con = sqlite3.connect(db_path)  # schema from the first version: no taken_at / suggestions / description
    con.executescript("""
        CREATE TABLE users (id VARCHAR PRIMARY KEY, google_sub VARCHAR, email VARCHAR, name VARCHAR, picture VARCHAR, created_at DATETIME);
        CREATE TABLE categories (id VARCHAR PRIMARY KEY, user_id VARCHAR, name VARCHAR, color VARCHAR, source VARCHAR, created_at DATETIME);
        CREATE TABLE documents (id VARCHAR PRIMARY KEY, user_id VARCHAR, filename VARCHAR, mime VARCHAR, storage_key VARCHAR,
            kind VARCHAR, status VARCHAR, error TEXT, title VARCHAR, summary TEXT, caption TEXT, ocr_text TEXT,
            category_id VARCHAR, category_confidence FLOAT, category_method VARCHAR, category_confirmed BOOLEAN,
            favorite BOOLEAN, created_at DATETIME);
        INSERT INTO documents (id, user_id, filename, mime, storage_key, status) VALUES ('d1', 'u1', 'a.png', 'image/png', 'k', 'ready');
    """)
    con.commit()
    con.close()

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app import db
    from app.config import get_settings

    get_settings.cache_clear()
    db.reset_engine()
    db.init_db()
    cols = {r[1] for r in sqlite3.connect(db_path).execute("PRAGMA table_info(documents)")}
    assert {"taken_at", "suggestions", "pending_category", "processing_started_at"} <= cols
    row = sqlite3.connect(db_path).execute("SELECT suggestions, pending_category FROM documents").fetchone()
    assert row == ("[]", "")
    db.reset_engine()
