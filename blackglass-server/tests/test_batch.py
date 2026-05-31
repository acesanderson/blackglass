from __future__ import annotations


def test_batch_mixed_paths(client):
    r = client.post("/vault/notes/batch", json={"paths": ["alpha.md", "ghost.md", "../escape.md"]})
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == {"ok": 1, "not_found": 1, "error": 1}
    statuses = [x["status"] for x in body["results"]]
    assert statuses == ["ok", "not_found", "error"]
    assert body["results"][1]["error"] == "not found"
    assert body["results"][2]["error"] == "path escapes vault"
    assert body["results"][0]["note"]["path"] == "alpha.md"


def test_batch_preserves_order_with_duplicates(client):
    r = client.post("/vault/notes/batch", json={"paths": ["alpha.md", "alpha.md", "beta.md"]})
    assert r.status_code == 200
    body = r.json()
    paths = [x["path"] for x in body["results"]]
    assert paths == ["alpha.md", "alpha.md", "beta.md"]


def test_batch_empty_list_400(client):
    r = client.post("/vault/notes/batch", json={"paths": []})
    assert r.status_code == 400


def test_batch_too_many_400(client):
    r = client.post("/vault/notes/batch", json={"paths": ["alpha.md"] * 51})
    assert r.status_code == 400
