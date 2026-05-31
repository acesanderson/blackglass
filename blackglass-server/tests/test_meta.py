from __future__ import annotations


def test_meta_existing_file(client):
    r = client.get("/vault/notes/beta.md/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["exists"] is True
    assert body["path"] == "beta.md"
    assert body["size"] > 0
    assert body["mtime"] is not None
    assert body["frontmatter"] == {"status": "in-progress", "tags": ["foo"]}
    assert body["tags"] == ["foo"]
    assert body["wikilinks_count"] == 1


def test_meta_missing_file_returns_200_with_exists_false(client):
    r = client.get("/vault/notes/ghost.md/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["exists"] is False
    assert body["size"] == 0
    assert body["mtime"] is None
    assert body["frontmatter"] == {}
    assert body["tags"] == []
    assert body["wikilinks_count"] == 0


def test_meta_path_escape_400(client):
    r = client.get("/vault/notes/..%2Fescape.md/meta")
    assert r.status_code == 400


def test_meta_directory_400(client):
    r = client.get("/vault/notes/Work Docs/meta")
    assert r.status_code == 400


def test_meta_wikilinks_count_includes_duplicates(client, vault):
    (vault / "linky.md").write_text("[[a]] [[a]] [[b]] [[a|alias]]")
    r = client.get("/vault/notes/linky.md/meta")
    assert r.json()["wikilinks_count"] == 4
