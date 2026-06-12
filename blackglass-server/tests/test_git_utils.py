from __future__ import annotations
import subprocess
from blackglass_server.git_utils import parse_name_status, parse_numstat, git_commit_and_push


def test_parse_name_status_added_modified():
    raw = "abc123\x1f1780115422\x1fmodify alpha\x1eM\talpha.md\x1edef456\x1f1780115000\x1fadd epsilon\x1eA\tepsilon.md"
    out = parse_name_status(raw)
    assert len(out) == 2
    assert out[0]["commit"] == "abc123"
    assert out[0]["timestamp"] == 1780115422.0
    assert out[0]["subject"] == "modify alpha"
    assert out[0]["changes"] == [{"change": "modified", "path": "alpha.md", "from_path": None}]


def test_parse_name_status_renamed():
    raw = "c1\x1f100\x1fr1\x1eR100\told.md\tnew.md"
    out = parse_name_status(raw)
    assert out[0]["changes"][0] == {"change": "renamed", "path": "new.md", "from_path": "old.md"}


def test_parse_numstat_basic():
    raw = "c1\x1f100\x1fr1\x1e3\t1\talpha.md\n0\t0\tbinary.png"
    out = parse_numstat(raw)
    assert out["c1"] == {"alpha.md": {"added": 3, "removed": 1}}


def test_git_commit_and_push_update(git_vault):
    (git_vault / "epsilon.md").write_text("updated content")
    git_commit_and_push(git_vault, ["epsilon.md"], "update")
    proc = subprocess.run(
        ["git", "-C", str(git_vault), "log", "-n", "1", "--pretty=format:%s"],
        capture_output=True, text=True, check=True
    )
    assert proc.stdout.strip() == "api: update epsilon.md"


def test_git_commit_and_push_create(git_vault):
    (git_vault / "omega.md").write_text("omega content")
    git_commit_and_push(git_vault, ["omega.md"], "create")
    proc = subprocess.run(
        ["git", "-C", str(git_vault), "log", "-n", "1", "--pretty=format:%s"],
        capture_output=True, text=True, check=True
    )
    assert proc.stdout.strip() == "api: create omega.md"


def test_git_commit_and_push_delete(git_vault):
    (git_vault / "epsilon.md").unlink()
    git_commit_and_push(git_vault, ["epsilon.md"], "delete")
    proc = subprocess.run(
        ["git", "-C", str(git_vault), "log", "-n", "1", "--pretty=format:%s"],
        capture_output=True, text=True, check=True
    )
    assert proc.stdout.strip() == "api: delete epsilon.md"


def test_git_commit_and_push_no_changes(git_vault):
    proc_before = subprocess.run(
        ["git", "-C", str(git_vault), "log", "-n", "1", "--pretty=format:%s"],
        capture_output=True, text=True, check=True
    )
    git_commit_and_push(git_vault, ["epsilon.md"], "update")
    proc_after = subprocess.run(
        ["git", "-C", str(git_vault), "log", "-n", "1", "--pretty=format:%s"],
        capture_output=True, text=True, check=True
    )
    assert proc_before.stdout == proc_after.stdout

