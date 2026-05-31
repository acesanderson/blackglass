from __future__ import annotations


def test_files_no_filter_returns_legacy_shape(client):
    r = client.get("/vault/files")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert all("path" in f and "size" in f for f in body)


def test_files_tag_filter(client):
    r = client.get("/vault/files", params={"tag": "foo"})
    body = r.json()
    paths = [f["path"] for f in body["files"]]
    assert set(paths) == {"beta.md", "gamma.md"}
    assert body["total"] == 2
    assert body["filtered_from"] >= 2


def test_files_tag_and_filter(client):
    r = client.get("/vault/files", params=[("tag", "foo"), ("tag", "bar")])
    body = r.json()
    paths = [f["path"] for f in body["files"]]
    assert paths == ["gamma.md"]


def test_files_fm_string(client):
    r = client.get("/vault/files", params={"fm.status": "in-progress"})
    paths = [f["path"] for f in r.json()["files"]]
    assert paths == ["beta.md"]


def test_files_fm_number(client):
    r = client.get("/vault/files", params={"fm.priority": "3"})
    paths = [f["path"] for f in r.json()["files"]]
    assert paths == ["gamma.md"]


def test_files_fm_bool(client):
    r = client.get("/vault/files", params={"fm.archived": "true"})
    paths = [f["path"] for f in r.json()["files"]]
    assert paths == ["delta.md"]


def test_files_path_glob_direct_children(client):
    r = client.get("/vault/files", params={"path_glob": "Work Docs/*.md"})
    paths = [f["path"] for f in r.json()["files"]]
    assert paths == ["Work Docs/foo.md"]


def test_files_path_glob_recursive(client):
    r = client.get("/vault/files", params={"path_glob": "Work Docs/**/*.md"})
    paths = sorted(f["path"] for f in r.json()["files"])
    assert paths == ["Work Docs/Sub/bar.md", "Work Docs/foo.md"]


def test_files_dup_fm_400(client):
    r = client.get("/vault/files", params=[("fm.status", "x"), ("fm.status", "y")])
    assert r.status_code == 400


def test_files_nested_fm_key_400(client):
    r = client.get("/vault/files", params={"fm.a.b": "x"})
    assert r.status_code == 400


def test_files_path_glob_dotdot_400(client):
    r = client.get("/vault/files", params={"path_glob": "../escape"})
    assert r.status_code == 400
