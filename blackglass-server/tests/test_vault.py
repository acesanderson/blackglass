import pytest
from pathlib import Path
from blackglass_server.vault import (
    read_note, write_note, delete_note, list_files,
    compute_backlinks, list_tags, list_periodic_notes,
    fulltext_search,
)


@pytest.fixture
def vault(tmp_path):
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "Note A.md").write_text("---\ntags: [foo]\n---\nSee [[Note B]].")
    (tmp_path / "Note B.md").write_text("No frontmatter.")
    (tmp_path / "2024-01-15.md").write_text("Daily note.")
    return tmp_path


def test_read_note(vault):
    note = read_note(vault, "Note A.md")
    assert note["frontmatter"] == {"tags": ["foo"]}
    assert "See [[Note B]]" in note["body"]
    assert note["wikilinks"] == ["Note B"]
    assert note["tags"] == ["foo"]


def test_read_note_missing(vault):
    with pytest.raises(FileNotFoundError):
        read_note(vault, "Ghost.md")


def test_write_and_read(vault):
    write_note(vault, "New.md", "---\ntitle: New\n---\nHello.")
    note = read_note(vault, "New.md")
    assert note["frontmatter"]["title"] == "New"


def test_delete_note(vault):
    delete_note(vault, "Note B.md")
    assert not (vault / "Note B.md").exists()


def test_delete_missing(vault):
    with pytest.raises(FileNotFoundError):
        delete_note(vault, "Ghost.md")


def test_list_files(vault):
    files = list_files(vault)
    paths = [f["path"] for f in files]
    assert "Note A.md" in paths
    assert "Note B.md" in paths


def test_list_files_excludes_obsidian(vault):
    (vault / ".obsidian" / "config.md").write_text("internal")
    files = list_files(vault)
    paths = [f["path"] for f in files]
    assert not any(".obsidian" in p for p in paths)


def test_compute_backlinks(vault):
    bl = compute_backlinks(vault, "Note B.md")
    assert "Note A.md" in bl


def test_list_tags(vault):
    tags = list_tags(vault)
    assert any(t["tag"] == "foo" for t in tags)


def test_list_periodic_notes(vault):
    periodic = list_periodic_notes(vault)
    assert any(p["path"] == "2024-01-15.md" for p in periodic)


def test_fulltext_search(vault):
    results = fulltext_search(vault, "Daily")
    assert any(r["path"] == "2024-01-15.md" for r in results)


def test_fulltext_search_no_results(vault):
    results = fulltext_search(vault, "xyznonexistent")
    assert results == []
