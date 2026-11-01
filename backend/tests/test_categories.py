import base64
import json

from app.describe import Description
from tests.conftest import login, png_bytes


def fake_describe(category: str, title: str = "Item", kind: str = "photo"):
    def _d(db, user_id, jpeg, text, filename, cats):
        return Description(title=title, summary=f"{title} summary", caption=f"{title} caption", kind=kind, category=category)
    return _d


def up(client, h, monkeypatch, category: str | None, title="Item", name="x.png"):
    monkeypatch.setattr("app.ingest.extract_text", lambda data, mime: "")
    if category is not None:
        monkeypatch.setattr("app.describe.describe", fake_describe(category, title))
    r = client.post("/documents", headers=h, files={"files": (name, png_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    return client.get(f"/documents/{r.json()[0]['id']}", headers=h).json()


def cats(client, h):
    return {c["name"]: c for c in client.get("/categories", headers=h).json()}


def test_existing_category_pick_is_applied(client, monkeypatch):
    h = login(client)
    doc = up(client, h, monkeypatch, "Receipts & Bills")
    assert doc["category"]["name"] == "Receipts & Bills" and doc["category_method"] == "claude"


def test_new_category_is_suggested_then_grouped_on_second_item(client, monkeypatch):
    h = login(client)
    first = up(client, h, monkeypatch, "Gym Progress", "Squat log")
    assert first["category"] is None
    assert first["suggestions"][0] == {"category_id": None, "name": "Gym Progress", "score": 0.7, "source": "claude-new"}

    sugg = client.get("/categories/suggestions", headers=h).json()
    assert sugg["proposed"][0]["name"] == "Gym Progress" and sugg["unfiled"] == 1

    second = up(client, h, monkeypatch, "gym progress", "Bench log")
    assert second["category"]["name"] == "Gym Progress" and second["category"]["source"] == "ai"
    first = client.get(f"/documents/{first['id']}", headers=h).json()
    assert first["category"]["name"] == "Gym Progress"  # grouped retroactively
    assert cats(client, h)["Gym Progress"]["count"] == 2


def test_accept_new_suggestion_and_bulk(client, monkeypatch):
    h = login(client)
    a = up(client, h, monkeypatch, "Concert Tickets", "Ticket A")
    r = client.patch(f"/documents/{a['id']}", json={"new_category_name": "Concert Tickets"}, headers=h).json()
    assert r["category"]["name"] == "Concert Tickets" and r["category_confirmed"]

    b = up(client, h, monkeypatch, "Plants", "Fern")
    r = client.post("/documents/bulk", json={"document_ids": [b["id"]], "action": "accept_suggestions"}, headers=h)
    assert r.json() == {"updated": 1}
    assert client.get(f"/documents/{b['id']}", headers=h).json()["category"]["name"] == "Plants"

    trips = cats(client, h)["Family & Trips"]["id"]
    client.post("/documents/bulk", json={"document_ids": [a["id"], b["id"]], "action": "categorize", "category_id": trips}, headers=h)
    assert cats(client, h)["Family & Trips"]["count"] == 2
    assert len(cats(client, h)["Family & Trips"]["covers"]) == 2

    client.post("/documents/bulk", json={"document_ids": [a["id"]], "action": "delete"}, headers=h)
    assert client.get(f"/documents/{a['id']}", headers=h).status_code == 404


def test_custom_category_with_items_and_merge(client, monkeypatch):
    h = login(client)
    d = up(client, h, monkeypatch, "Something Else")
    r = client.post("/categories", json={"name": "Travel", "description": "trips and holidays", "color": "#3d4f86",
                                         "document_ids": [d["id"]]}, headers=h)
    assert r.status_code == 200 and r.json()["description"] == "trips and holidays"
    assert client.post("/categories", json={"name": "Travel"}, headers=h).status_code == 409
    assert client.post("/categories", json={"name": "Bad", "color": "red"}, headers=h).status_code == 422

    dup = client.post("/categories", json={"name": "travel"}, headers=h).json()  # case differs: allowed but similar
    merges = client.get("/categories/suggestions", headers=h).json()["merges"]
    pair = {merges[0]["source"]["name"], merges[0]["target"]["name"]}
    assert pair == {"Travel", "travel"} and merges[0]["reason"] == "Similar names"

    travel = cats(client, h)["Travel"]["id"]
    merged = client.post(f"/categories/{dup['id']}/merge", json={"into_id": travel}, headers=h).json()
    assert merged["name"] == "Travel" and merged["count"] == 1
    assert "travel" not in cats(client, h)


def test_search_filters_returned(client, monkeypatch):
    h = login(client)
    up(client, h, monkeypatch, "Family & Trips")
    r = client.get("/search", params={"q": "photos from last year"}, headers=h).json()
    assert r["filters"]["kind"] == "photo" and r["filters"]["parsed_by"] == "rules"


def test_worker_push_processes_once(client, monkeypatch):
    from fastapi.testclient import TestClient

    from app.worker import app as worker_app

    calls = []
    monkeypatch.setattr("app.describe.describe", lambda *a, **k: calls.append(1) or None)
    monkeypatch.setattr("app.ingest.extract_text", lambda data, mime: "")
    monkeypatch.setattr("app.tasks.enqueue", lambda bg, ids: None)  # simulate pubsub: API doesn't process
    monkeypatch.setattr("app.routers.documents.enqueue", lambda bg, ids: None)
    h = login(client)
    doc_id = client.post("/documents", headers=h, files={"files": ("a.png", png_bytes(), "image/png")}).json()[0]["id"]
    assert client.get(f"/documents/{doc_id}", headers=h).json()["status"] == "pending"

    msg = {"message": {"data": base64.b64encode(json.dumps({"document_id": doc_id}).encode()).decode()}}
    with TestClient(worker_app) as w:
        assert w.post("/pubsub/push", json=msg).status_code == 204
        assert w.post("/pubsub/push", json=msg).status_code == 204  # duplicate delivery
        assert w.post("/pubsub/push", json={"message": {"data": "!!"}}).status_code == 204  # malformed: acked
    assert client.get(f"/documents/{doc_id}", headers=h).json()["status"] == "ready"
    assert len(calls) == 1  # Claude called once despite duplicate
