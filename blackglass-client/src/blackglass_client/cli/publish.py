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


_GITHUB_BASE = "https://api.github.com"


def create_gist(
    token: str, filename: str, content: str, description: str, public: bool
) -> dict:
    """Create a GitHub Gist. Returns the API response dict."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    payload = {
        "description": description,
        "public": public,
        "files": {filename: {"content": content}},
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{_GITHUB_BASE}/gists", headers=headers, json=payload)
        if resp.status_code >= 400:
            detail = resp.text
            try:
                body = resp.json()
                detail = body.get("message", detail)
            except ValueError:
                pass
            click.echo(f"GitHub API error: {detail}", err=True)
            sys.exit(1)
        return resp.json()
