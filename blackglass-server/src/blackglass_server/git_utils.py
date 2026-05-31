from __future__ import annotations
import subprocess
from pathlib import Path

_CHANGE_LETTER = {
    "A": "added",
    "M": "modified",
    "D": "deleted",
    "R": "renamed",
    "C": "copied",
    "T": "type_changed",
}


def _parse_file_lines(lines: list[str]) -> list[dict]:
    changes = []
    for line in lines:
        if not line:
            continue
        cols = line.split("\t")
        letter = cols[0][:1]
        change = _CHANGE_LETTER.get(letter)
        if change is None:
            continue
        if change in ("renamed", "copied") and len(cols) >= 3:
            from_path, path = cols[1], cols[2]
        else:
            from_path = None
            path = cols[1] if len(cols) >= 2 else ""
        try:
            path.encode("utf-8")
        except UnicodeError:
            continue
        changes.append({"change": change, "path": path, "from_path": from_path})
    return changes


def parse_name_status(raw: str) -> list[dict]:
    """Parse git log --name-status --pretty=format:'%H%x1f%ct%x1f%s%x1e' output.

    git appends x1e to each pretty record; --name-status lines follow each
    record, separated by blank lines. When split on x1e the output interleaves
    header tokens and file-status lines. We accumulate file lines and attach
    them to the most-recently-seen header.
    """
    commits: list[dict] = []
    if not raw:
        return commits

    current: dict | None = None
    pending_lines: list[str] = []

    def _flush() -> None:
        if current is not None:
            current["changes"] = _parse_file_lines(pending_lines)
            commits.append(current)
        pending_lines.clear()

    for chunk in raw.split("\x1e"):
        for line in chunk.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\x1f")
            if len(parts) == 3:
                # This is a commit header: hash\x1fts\x1fsubject
                _flush()
                commit, ts_str, subject = parts
                try:
                    ts = float(ts_str)
                except ValueError:
                    current = None
                    continue
                current = {"commit": commit, "timestamp": ts, "subject": subject, "changes": []}
                pending_lines.clear()
            else:
                # File status line (or blank, already stripped above)
                pending_lines.append(line)

    _flush()
    return commits


def parse_numstat(raw: str) -> dict[str, dict[str, dict[str, int]]]:
    """Parse git log --numstat --pretty=format:'%H%x1f%ct%x1f%s%x1e' output."""
    out: dict[str, dict[str, dict[str, int]]] = {}
    if not raw:
        return out

    current_commit: str | None = None
    per_file: dict[str, dict[str, int]] = {}

    def _flush() -> None:
        if current_commit is not None:
            out[current_commit] = dict(per_file)
        per_file.clear()

    for chunk in raw.split("\x1e"):
        for line in chunk.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\x1f")
            if len(parts) == 3:
                _flush()
                current_commit = parts[0]
                per_file.clear()
            else:
                cols = line.split("\t")
                if len(cols) < 3:
                    continue
                added_s, removed_s, path = cols[0], cols[1], cols[2]
                try:
                    added = int(added_s)
                    removed = int(removed_s)
                except ValueError:
                    # Binary files show as '-\t-'; skip them.
                    continue
                if added == 0 and removed == 0:
                    continue
                per_file[path] = {"added": added, "removed": removed}

    _flush()
    return out


def git_changes(
    vault_path: Path,
    since_epoch: float,
    include_diff_stats: bool = False,
    timeout: float = 10.0,
) -> list[dict]:
    pretty = "--pretty=format:%H\x1f%ct\x1f%s\x1e"
    proc = subprocess.run(
        ["git", "-C", str(vault_path), "log", f"--since={int(since_epoch)}",
         "--name-status", pretty],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git log failed")
    commits = parse_name_status(proc.stdout)
    if include_diff_stats:
        proc2 = subprocess.run(
            ["git", "-C", str(vault_path), "log", f"--since={int(since_epoch)}",
             "--numstat", pretty],
            capture_output=True, text=True, timeout=timeout,
        )
        if proc2.returncode == 0:
            stats = parse_numstat(proc2.stdout)
            for c in commits:
                per_file = stats.get(c["commit"], {})
                for ch in c["changes"]:
                    ch["diff_stats"] = per_file.get(ch["path"])
    return commits
