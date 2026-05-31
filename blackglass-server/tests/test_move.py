from __future__ import annotations
import pytest


@pytest.fixture(autouse=True)
def stub_embedding_update(monkeypatch):
    calls = []
    async def fake_update(old, new):
        calls.append((old, new))
    from blackglass_server import db as db_mod
    monkeypatch.setattr(db_mod, "update_embedding_path", fake_update)
    return calls


def test_move_renames_file(client, vault):
    (vault / "src.md").write_text("hello")
    r = client.post("/vault/notes/src.md/move", json={"to": "dest.md", "rewrite_links": False})
    assert r.status_code == 200
    body = r.json()
    assert body["from"] == "src.md"
    assert body["to"] == "dest.md"
    assert (vault / "dest.md").read_text() == "hello"
    assert not (vault / "src.md").exists()
    assert "db_error" not in body


def test_move_with_link_rewrite(client, vault):
    (vault / "src.md").write_text("body")
    (vault / "ref.md").write_text("see [[src]] and [[src|alias]] and ![[src]] and [[src#h]]")
    r = client.post("/vault/notes/src.md/move", json={"to": "dest.md"})
    body = r.json()
    assert "ref.md" in body["rewrote_links_in"]
    text = (vault / "ref.md").read_text()
    assert text == "see [[dest]] and [[dest|alias]] and ![[dest]] and [[dest#h]]"


def test_move_dest_exists_409(client, vault):
    (vault / "src.md").write_text("a")
    (vault / "dest.md").write_text("b")
    r = client.post("/vault/notes/src.md/move", json={"to": "dest.md"})
    assert r.status_code == 409


def test_move_source_missing_404(client, vault):
    r = client.post("/vault/notes/ghost.md/move", json={"to": "dest.md"})
    assert r.status_code == 404


def test_move_stem_collision_flag(client, vault):
    (vault / "src.md").write_text("a")
    (vault / "Other").mkdir()
    (vault / "Other" / "src.md").write_text("b")
    r = client.post("/vault/notes/src.md/move", json={"to": "dest.md"})
    body = r.json()
    assert body["stem_collision"] is True
    assert "Other/src.md" in body["stem_collision_paths"]


def test_move_db_called(client, vault, stub_embedding_update):
    (vault / "src.md").write_text("a")
    client.post("/vault/notes/src.md/move", json={"to": "dest.md", "rewrite_links": False})
    assert ("src.md", "dest.md") in stub_embedding_update


def test_move_to_escape_400(client, vault):
    (vault / "src.md").write_text("a")
    r = client.post("/vault/notes/src.md/move", json={"to": "../escape.md"})
    assert r.status_code == 400


def test_move_block_reference_rewritten(client, vault):
    (vault / "src.md").write_text("body")
    (vault / "ref.md").write_text("see [[src#^abc123]] and ![[src#^xyz]]")
    r = client.post("/vault/notes/src.md/move", json={"to": "dest.md"})
    assert r.status_code == 200
    assert (vault / "ref.md").read_text() == "see [[dest#^abc123]] and ![[dest#^xyz]]"


def test_move_full_path_wikilink_rewritten(client, vault):
    (vault / "Path").mkdir()
    (vault / "Path" / "To").mkdir()
    (vault / "Path" / "To" / "old.md").write_text("body")
    (vault / "ref.md").write_text("see [[Path/To/old]] and [[Path/To/old|alias]] and [[Path/To/old#h]]")
    r = client.post("/vault/notes/Path/To/old.md/move", json={"to": "New/Loc/dest.md"})
    assert r.status_code == 200
    assert (vault / "ref.md").read_text() == "see [[New/Loc/dest]] and [[New/Loc/dest|alias]] and [[New/Loc/dest#h]]"


def test_move_root_file_stem_only_no_double_match(client, vault):
    # Note at vault root: stem == full-path-no-ext == "src".
    # Dedup logic must not double-rewrite the link.
    (vault / "src.md").write_text("body")
    (vault / "ref.md").write_text("see [[src]]")
    r = client.post("/vault/notes/src.md/move", json={"to": "dest.md"})
    assert r.status_code == 200
    assert (vault / "ref.md").read_text() == "see [[dest]]"


def test_move_source_escape_400(client, vault):
    r = client.post("/vault/notes/..%2Fescape.md/move", json={"to": "dest.md"})
    assert r.status_code == 400


def test_move_rename_fails_500(client, vault, monkeypatch):
    (vault / "src.md").write_text("a")
    from blackglass_server import vault as vault_mod
    def fake_move(vault_path, old_rel, new_rel):
        raise PermissionError("simulated")
    monkeypatch.setattr(vault_mod, "move_note", fake_move)
    r = client.post("/vault/notes/src.md/move", json={"to": "dest.md"})
    assert r.status_code == 500
    # Source file should still exist (move_note was patched to fail before rename)
    assert (vault / "src.md").exists()
