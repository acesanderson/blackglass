from __future__ import annotations

import re

import yaml

_FM_RE = re.compile(r"^---[ \t]*\n(.*?)\n---[ \t]*\n?", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def split_frontmatter(text: str) -> tuple[dict, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(fm, dict):
        return {}, text
    body = text[m.end():].lstrip()
    return fm, body


def extract_wikilinks(body: str) -> list[str]:
    return _WIKILINK_RE.findall(body)


def extract_tags(frontmatter: dict) -> list[str]:
    val = frontmatter.get("tags", [])
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        return [val]
    return []
