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


_SNIPPET_LOOKBACK = 50


def snippet_from_body(body: str, snippet_chars: int) -> str:
    if snippet_chars <= 0:
        return ""
    stripped = body.lstrip()
    if len(stripped) <= snippet_chars:
        return stripped
    window = stripped[: snippet_chars + 100]
    if snippet_chars < len(window) and window[snippet_chars - 1] in " \t\n":
        return window[:snippet_chars].rstrip()
    cut = window.rfind(" ", max(0, snippet_chars - _SNIPPET_LOOKBACK), snippet_chars)
    if cut == -1:
        cut2 = window.rfind("\n", max(0, snippet_chars - _SNIPPET_LOOKBACK), snippet_chars)
        if cut2 == -1:
            return window[:snippet_chars]
        cut = cut2
    return window[:cut].rstrip()
