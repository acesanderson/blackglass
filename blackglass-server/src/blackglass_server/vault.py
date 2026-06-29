from __future__ import annotations
import datetime
import glob as _glob
import logging
import re
import stat as _stat
import zoneinfo
from pathlib import Path
from pathlib import PurePosixPath
from .text_utils import split_frontmatter, extract_wikilinks, extract_tags

_log = logging.getLogger(__name__)

_PERIODIC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
_SKIP_DIRS = {".obsidian", ".trash"}


def _skip(p: Path) -> bool:
    return bool(_SKIP_DIRS & set(p.parts)) or "/" in str(p.relative_to(p.parent))


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


def _fm_value_matches(fm_value, query: str) -> bool:
    if isinstance(fm_value, dict):
        _log.warning("fm filter skipped dict value")
        return False
    if isinstance(fm_value, list):
        return any(_fm_value_matches(v, query) for v in fm_value)
    if isinstance(fm_value, bool):
        return query == ("true" if fm_value else "false")
    if isinstance(fm_value, (int, float)) and not isinstance(fm_value, bool):
        try:
            return float(query) == float(fm_value)
        except ValueError:
            return False
    return str(fm_value) == query


def list_files_filtered(
    vault_path: Path,
    tags: list[str] | None = None,
    fm_filters: dict[str, str] | None = None,
    path_glob: str | None = None,
    limit: int | None = None,
) -> tuple[list[dict], int, int]:
    tags = tags or []
    fm_filters = fm_filters or {}
    all_files = list_files(vault_path)
    # Known spec deviation: glob.translate never raises on malformed patterns
    # (it escapes invalid constructs into literal regex chars), so the spec's
    # "path_glob parse error -> 400" failure mode is unachievable here. Patterns
    # silently become valid-but-likely-wrong filters. Documented in Task 5.
    glob_re = re.compile(_glob.translate(path_glob, recursive=True, include_hidden=True)) if path_glob is not None else None
    filtered: list[dict] = []
    for f in all_files:
        rel = f["path"]
        if glob_re is not None and not glob_re.match(rel):
            continue
        if tags or fm_filters:
            text = (vault_path / rel).read_text(encoding="utf-8", errors="ignore")
            fm, _ = split_frontmatter(text)
            file_tags = set(extract_tags(fm))
            if tags and not all(t in file_tags for t in tags):
                continue
            ok = True
            for key, val in fm_filters.items():
                if key not in fm or not _fm_value_matches(fm[key], val):
                    ok = False
                    break
            if not ok:
                continue
        filtered.append(f)
    total_before_limit = len(filtered)
    if limit is not None:
        filtered = filtered[:limit]
    return filtered, total_before_limit, len(all_files)


def ensure_daily_note(vault_path: Path, date_str: str) -> tuple[Path, bool]:
    validate_date_str(date_str)
    p = vault_path / f"{date_str}.md"
    created = not p.exists()
    if created:
        p.touch(exist_ok=True)
    return p, created


def _wikilink_patterns(
    old_stem: str, new_stem: str,
    old_full: str, new_full: str,
) -> list[tuple[re.Pattern, str]]:
    # Build stem-only patterns plus full-path patterns.
    # Dedup when the note sits at vault root (stem == full-path-no-ext).
    pairs = [(old_stem, new_stem)]
    if old_full != old_stem:
        pairs.append((old_full, new_full))
    pats: list[tuple[re.Pattern, str]] = []
    for old, new in pairs:
        o = re.escape(old)
        n = new.replace("\\", r"\\")
        pats.extend([
            (re.compile(rf"(!?)\[\[{o}\]\]"), rf"\1[[{n}]]"),
            (re.compile(rf"(!?)\[\[{o}\|([^\]]+)\]\]"), rf"\1[[{n}|\2]]"),
            (re.compile(rf"(!?)\[\[{o}#([^\]\|]+)\]\]"), rf"\1[[{n}#\2]]"),
            (re.compile(rf"(!?)\[\[{o}#([^\]\|]+)\|([^\]]+)\]\]"), rf"\1[[{n}#\2|\3]]"),
        ])
    return pats


def rewrite_wikilinks(
    vault_path: Path,
    old_rel: str,
    new_rel: str,
) -> tuple[list[str], list[dict]]:
    old_stem = Path(old_rel).stem
    new_stem = Path(new_rel).stem
    old_full = str(Path(old_rel).with_suffix(""))
    new_full = str(Path(new_rel).with_suffix(""))
    patterns = _wikilink_patterns(old_stem, new_stem, old_full, new_full)
    rewrote: list[str] = []
    errors: list[dict] = []
    for p in vault_path.rglob("*.md"):
        if _skip(p):
            continue
        if str(p.relative_to(vault_path)) in (old_rel, new_rel):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            errors.append({"path": str(p.relative_to(vault_path)), "error_class": type(exc).__name__})
            continue
        new_text = text
        for pat, repl in patterns:
            new_text = pat.sub(repl, new_text)
        if new_text != text:
            try:
                p.write_text(new_text, encoding="utf-8")
                rewrote.append(str(p.relative_to(vault_path)))
            except OSError as exc:
                errors.append({"path": str(p.relative_to(vault_path)), "error_class": type(exc).__name__})
    return rewrote, errors


def find_stem_collisions(vault_path: Path, old_rel: str) -> list[str]:
    target_stem = Path(old_rel).stem
    out = []
    for p in vault_path.rglob("*.md"):
        if _skip(p):
            continue
        rel = str(p.relative_to(vault_path))
        if rel == old_rel:
            continue
        if Path(rel).stem == target_stem:
            out.append(rel)
    return out


def move_note(
    vault_path: Path,
    old_rel: str,
    new_rel: str,
) -> None:
    src = _resolve(vault_path, old_rel)
    dst = _resolve(vault_path, new_rel)
    if not src.exists():
        raise FileNotFoundError(old_rel)
    if dst.exists():
        raise FileExistsError(new_rel)
    if src == dst:
        raise ValueError("source equals destination")
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)


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
