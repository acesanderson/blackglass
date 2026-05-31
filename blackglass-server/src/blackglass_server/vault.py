from __future__ import annotations
import datetime
import re
import stat as _stat
import zoneinfo
from pathlib import Path
from .text_utils import split_frontmatter, extract_wikilinks, extract_tags

_PERIODIC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
_SKIP_DIRS = {".obsidian", ".trash"}


def _skip(p: Path) -> bool:
    return bool(_SKIP_DIRS & set(p.parts))


def _resolve(vault_path: Path, rel_path: str) -> Path:
    p = (vault_path / rel_path).resolve()
    vault = vault_path.resolve()
    if p != vault and vault not in p.parents:
        raise ValueError(f"Path escapes vault: {rel_path}")
    return p


def read_note(vault_path: Path, rel_path: str) -> dict:
    p = _resolve(vault_path, rel_path)
    if not p.exists():
        raise FileNotFoundError(rel_path)
    text = p.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    return {
        "path": rel_path,
        "content": text,
        "frontmatter": fm,
        "body": body,
        "wikilinks": extract_wikilinks(body),
        "tags": extract_tags(fm),
    }


def write_note(vault_path: Path, rel_path: str, content: str) -> None:
    p = _resolve(vault_path, rel_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def delete_note(vault_path: Path, rel_path: str) -> None:
    p = _resolve(vault_path, rel_path)
    if not p.exists():
        raise FileNotFoundError(rel_path)
    p.unlink()


def list_files(vault_path: Path) -> list[dict]:
    results = []
    for p in sorted(vault_path.rglob("*.md")):
        if _skip(p):
            continue
        rel = str(p.relative_to(vault_path))
        results.append({"path": rel, "size": p.stat().st_size})
    return results


def compute_backlinks(vault_path: Path, rel_path: str) -> list[str]:
    stem = Path(rel_path).stem
    backlinks = []
    for p in vault_path.rglob("*.md"):
        if _skip(p):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if f"[[{stem}]]" in text or f"[[{stem}|" in text:
            backlinks.append(str(p.relative_to(vault_path)))
    return backlinks


def list_tags(vault_path: Path) -> list[dict]:
    counts: dict[str, int] = {}
    for p in vault_path.rglob("*.md"):
        if _skip(p):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        fm, _ = split_frontmatter(text)
        for tag in extract_tags(fm):
            counts[tag] = counts.get(tag, 0) + 1
    return [{"tag": t, "count": c} for t, c in sorted(counts.items())]


def list_periodic_notes(vault_path: Path) -> list[dict]:
    results = []
    for p in vault_path.glob("*.md"):
        if _PERIODIC_RE.match(p.name):
            results.append({"path": p.name, "date": p.stem})
    return sorted(results, key=lambda x: x["date"], reverse=True)


_DATE_FMT = "%Y-%m-%d"
_MIN_DATE = datetime.date(1970, 1, 1)
_MAX_DATE = datetime.date(2099, 12, 31)


def today_in_tz(tz: str) -> str:
    return datetime.datetime.now(zoneinfo.ZoneInfo(tz)).strftime(_DATE_FMT)


def yesterday_in_tz(tz: str) -> str:
    now = datetime.datetime.now(zoneinfo.ZoneInfo(tz))
    return (now - datetime.timedelta(days=1)).strftime(_DATE_FMT)


def validate_date_str(date_str: str) -> None:
    try:
        d = datetime.datetime.strptime(date_str, _DATE_FMT).date()
    except ValueError as exc:
        raise ValueError(f"invalid date format, expected YYYY-MM-DD: {date_str}") from exc
    if d < _MIN_DATE or d > _MAX_DATE:
        raise ValueError(f"date out of range [{_MIN_DATE}, {_MAX_DATE}]")


def ensure_daily_note(vault_path: Path, date_str: str) -> tuple[Path, bool]:
    validate_date_str(date_str)
    p = vault_path / f"{date_str}.md"
    created = not p.exists()
    if created:
        p.touch(exist_ok=True)
    return p, created


def fulltext_search(vault_path: Path, query: str) -> list[dict]:
    query_lower = query.lower()
    results = []
    for p in vault_path.rglob("*.md"):
        if _skip(p):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if query_lower in text.lower():
            idx = text.lower().index(query_lower)
            excerpt = text[max(0, idx - 100):idx + 200].strip()
            results.append({"path": str(p.relative_to(vault_path)), "excerpt": excerpt})
    return results


def note_meta(vault_path: Path, rel_path: str) -> dict:
    p = _resolve(vault_path, rel_path)
    try:
        st = p.stat()
    except FileNotFoundError:
        return {
            "path": rel_path,
            "exists": False,
            "size": 0,
            "mtime": None,
            "frontmatter": {},
            "tags": [],
            "wikilinks_count": 0,
        }
    if _stat.S_ISDIR(st.st_mode):
        raise IsADirectoryError(rel_path)
    text = p.read_text(encoding="utf-8", errors="ignore")
    fm, body = split_frontmatter(text)
    return {
        "path": rel_path,
        "exists": True,
        "size": st.st_size,
        "mtime": st.st_mtime,
        "frontmatter": fm,
        "tags": extract_tags(fm),
        "wikilinks_count": body.count("[["),
    }
