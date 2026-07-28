from __future__ import annotations
import os
import re
import sys
from datetime import date

import click
import httpx


def strip_frontmatter(content: str) -> str:
    """Strip YAML frontmatter between first --- delimiters."""
    if not content.startswith("---"):
        return content
    lines = content.split("\n")
    if lines[0].strip() != "---":
        return content
    # Find the closing --- delimiter line.
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            body = "\n".join(lines[i + 1:])
            return body.lstrip("\n")
    # No closing delimiter: not valid frontmatter, return unchanged.
    return content


def get_note_date(content: str) -> str:
    """Extract date from frontmatter, fall back to today."""
    if content.startswith("---"):
        lines = content.split("\n", 1)
        if len(lines) >= 2:
            match = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})", lines[1], re.MULTILINE)
            if match:
                return match.group(1)
    return date.today().isoformat()
