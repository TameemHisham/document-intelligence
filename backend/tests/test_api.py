import numpy as np

from app.embeddings import clip_text
from tests.conftest import login, png_bytes

WARRANTY = (
    "CERTIFICATE OF WARRANTY. Dyson Pure Cool TP07. Purchase date: 14 November 2024. "
    "This product is guaranteed for 2 years from the date of purchase."
)


def upload(client, headers, name, monkeypatch, text=""):
    monkeypatch.setattr("app.ingest.extract_text", lambda data, mime: text)
    r = client.post("/documents", headers=headers, files={"files": (name, png_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    return r.json()[0]["id"]


def test_upload_search_ask_flow(client, monkeypatch):
    h = login(client)
    wid = upload(client, h, "dyson_warranty.png", monkeypatch, WARRANTY)
    upload(client, h, "mountain_hike.png", monkeypatch, "")

    doc = client.get(f"/documents/{wid}", headers=h).json()
    assert doc["status"] == "ready", doc["error"]
    assert {"field": "expiry_date", "label": "Expires", "value": "2026-11-14"} in doc["fields"]

    hits = client.get("/search", params={"q": "warranty guaranteed"}, headers=h).json()["results"]
    assert hits and hits[0]["document"]["id"] == wid
    assert "text" in hits[0]["matched"]

    ans = client.post("/ask", json={"question": "when does the warranty expire", "document_ids": [wid]}, headers=h).json()
    assert ans["sources"] and ans["sources"][0]["document_id"] == wid

    # file served via scoped token
    r = client.get(doc["file_url"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_projects_scope_and_ownership(client, monkeypatch):
    h = login(client)
    wid = upload(client, h, "warranty.png", monkeypatch, WARRANTY)
    p = client.post("/projects", json={"name": "Appliances"}, headers=h).json()
    p = client.post(f"/projects/{p['id']}/documents", json={"document_ids": [wid]}, headers=h).json()
    assert p["document_count"] == 1

    ans = client.post("/ask", json={"question": "warranty", "project_id": p["id"]}, headers=h).json()
    assert ans["sources"][0]["document_id"] == wid

    other = login(client, "b@example.com")
    assert client.get(f"/documents/{wid}", headers=other).status_code == 404
    assert client.get(f"/projects/{p['id']}", headers=other).status_code == 404
    assert client.get("/search", params={"q": "warranty"}, headers=other).json()["results"] == []
    assert client.get("/documents", headers={}).status_code == 401


def test_file_token_is_scoped_to_one_document(client, monkeypatch):
    h = login(client)
    a = upload(client, h, "a.png", monkeypatch)
    b = upload(client, h, "b.png", monkeypatch)
    url_a = client.get(f"/documents/{a}", headers=h).json()["file_url"]
    token = url_a.split("t=")[1]
    assert client.get(f"/documents/{b}/file", params={"t": token}).status_code == 403


def test_confirmed_categories_train_classifier(client, monkeypatch):
    from app import classifier
    from app.db import SessionLocal
    from app.models import User

    h = login(client)
    cats = {c["name"]: c["id"] for c in client.get("/categories", headers=h).json()}
    receipts, trips = cats["Receipts & Bills"], cats["Family & Trips"]
    for i in range(3):
        monkeypatch.setattr("app.ingest.clip_image", lambda img, fake_hint="": clip_text(["receipt total paid"]))
        d = upload(client, h, f"r{i}.png", monkeypatch)
        client.patch(f"/documents/{d}", json={"category_id": receipts}, headers=h)
        monkeypatch.setattr("app.ingest.clip_image", lambda img, fake_hint="": clip_text(["beach family holiday"]))
        d = upload(client, h, f"t{i}.png", monkeypatch)
        client.patch(f"/documents/{d}", json={"category_id": trips}, headers=h)

    db = SessionLocal()
    user = db.query(User).one()
    a = classifier.learned(db, user.id, np.asarray(clip_text(["receipt total paid"])[0]))
    db.close()
    assert a is not None and a.method == "classifier" and a.category_id == receipts


def test_delete_removes_from_search(client, monkeypatch):
    h = login(client)
    wid = upload(client, h, "warranty.png", monkeypatch, WARRANTY)
    assert client.delete(f"/documents/{wid}", headers=h).status_code == 204
    assert client.get("/search", params={"q": "warranty guaranteed"}, headers=h).json()["results"] == []
