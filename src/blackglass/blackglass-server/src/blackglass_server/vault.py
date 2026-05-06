from __future__ import annotations
import re
from pathlib import Path
from .text_utils import split_frontmatter, extract_wikilinks, extract_tags

_PERIODIC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")


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
        if ".obsidian" in p.parts:
            continue
        rel = str(p.relative_to(vault_path))
        results.append({"path": rel, "size": p.stat().st_size})
    return results


def compute_backlinks(vault_path: Path, rel_path: str) -> list[str]:
    stem = Path(rel_path).stem
    backlinks = []
    for p in vault_path.rglob("*.md"):
        if ".obsidian" in p.parts:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if f"[[{stem}]]" in text or f"[[{stem}|" in text:
            backlinks.append(str(p.relative_to(vault_path)))
    return backlinks


def list_tags(vault_path: Path) -> list[dict]:
    counts: dict[str, int] = {}
    for p in vault_path.rglob("*.md"):
        if ".obsidian" in p.parts:
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


def fulltext_search(vault_path: Path, query: str) -> list[dict]:
    query_lower = query.lower()
    results = []
    for p in vault_path.rglob("*.md"):
        if ".obsidian" in p.parts:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if query_lower in text.lower():
            idx = text.lower().index(query_lower)
            excerpt = text[max(0, idx - 100):idx + 200].strip()
            results.append({"path": str(p.relative_to(vault_path)), "excerpt": excerpt})
    return results
