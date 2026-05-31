from __future__ import annotations


def test_replace_unique_ok(client, vault):
    (vault / "simple.md").write_text("alpha beta gamma")
    r = client.patch("/vault/notes/simple.md", json={
        "op": "replace", "old": "beta", "new": "DELTA"
    })
    assert r.status_code == 200
    body = r.json()
    assert body["replacements"] == 1
    assert (vault / "simple.md").read_text() == "alpha DELTA gamma"


def test_replace_not_found_404(client, vault):
    (vault / "simple.md").write_text("alpha beta gamma")
    r = client.patch("/vault/notes/simple.md", json={
        "op": "replace", "old": "zeta", "new": "X"
    })
    assert r.status_code == 404
    assert (vault / "simple.md").read_text() == "alpha beta gamma"


def test_replace_ambiguous_409(client, vault):
    (vault / "many.md").write_text("x x x")
    r = client.patch("/vault/notes/many.md", json={
        "op": "replace", "old": "x", "new": "y"
    })
    assert r.status_code == 409
    body = r.json()
    assert body["detail"]["match_count"] == 3
    assert (vault / "many.md").read_text() == "x x x"


def test_replace_all_ok(client, vault):
    (vault / "many.md").write_text("x x x")
    r = client.patch("/vault/notes/many.md", json={
        "op": "replace", "old": "x", "new": "y", "replace_all": True
    })
    assert r.status_code == 200
    assert r.json()["replacements"] == 3
    assert (vault / "many.md").read_text() == "y y y"


def test_replace_empty_old_400(client, vault):
    (vault / "x.md").write_text("a")
    r = client.patch("/vault/notes/x.md", json={
        "op": "replace", "old": "", "new": "X"
    })
    assert r.status_code == 400


def test_replace_deletes_when_new_empty(client, vault):
    (vault / "x.md").write_text("hello world")
    r = client.patch("/vault/notes/x.md", json={
        "op": "replace", "old": "world", "new": ""
    })
    assert r.status_code == 200
    assert (vault / "x.md").read_text() == "hello "


def test_replace_multiline_section(client, vault):
    (vault / "doc.md").write_text("# Top\n## Tasks\nold body\n## Next\ntail")
    r = client.patch("/vault/notes/doc.md", json={
        "op": "replace",
        "old": "## Tasks\nold body\n## Next",
        "new": "## Tasks\nnew body line 1\nnew body line 2\n## Next",
    })
    assert r.status_code == 200
    assert "new body line 1" in (vault / "doc.md").read_text()


def test_replace_crlf_does_not_match_lf(client, vault):
    (vault / "lf.md").write_text("a\nb\nc")
    r = client.patch("/vault/notes/lf.md", json={
        "op": "replace", "old": "a\r\nb", "new": "Z"
    })
    assert r.status_code == 404


def test_replace_old_too_large_413(client, vault):
    (vault / "x.md").write_text("a")
    r = client.patch("/vault/notes/x.md", json={
        "op": "replace", "old": "x" * (1024 * 1024 + 1), "new": "y"
    })
    assert r.status_code == 413


def test_replace_result_too_large_413(client, vault):
    # Start with ~9.99 MiB file, replace a short token to expand past 10 MiB.
    base = "x" * (10 * 1024 * 1024 - 100)
    (vault / "big.md").write_text(base + "REPLACE_TARGET")
    original = (vault / "big.md").read_text()
    r = client.patch("/vault/notes/big.md", json={
        "op": "replace",
        "old": "REPLACE_TARGET",
        "new": "Y" * 200,  # adds 186 bytes, pushing total over 10 MiB
    })
    assert r.status_code == 413
    # File unchanged on disk
    assert (vault / "big.md").read_text() == original


def test_replace_new_too_large_413(client, vault):
    (vault / "x.md").write_text("hello")
    r = client.patch("/vault/notes/x.md", json={
        "op": "replace", "old": "hello", "new": "y" * (1024 * 1024 + 1)
    })
    assert r.status_code == 413
