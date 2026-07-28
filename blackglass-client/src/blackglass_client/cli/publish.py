from __future__ import annotations
import os
import re
import sys
from datetime import date

import click
import httpx

from ..client import request
from ._output import _emit


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


@click.command()
@click.argument("path")
@click.option("--private", is_flag=True, help="Create a private gist (default: public).")
def publish(path: str, private: bool) -> None:
    """Publish a note as a GitHub Gist."""
    token = os.environ.get("GITHUB_PERSONAL_TOKEN")
    if not token:
        click.echo("Error: GITHUB_PERSONAL_TOKEN environment variable is not set.", err=True)
        sys.exit(1)

    # Fetch note from blackglass
    note = request("GET", f"/vault/notes/{path}")
    content = note.get("content", "")

    # Strip frontmatter and extract date
    body = strip_frontmatter(content)
    pub_date = get_note_date(content)

    # Build gist metadata
    filename = path.rsplit("/", 1)[-1]  # handle paths with /
    title = filename.removesuffix(".md")
    description = f"{title} — published from Blackglass {pub_date}"

    # Create gist
    gist = create_gist(token, filename, body, description, not private)

    # Output result
    _emit(
        {
            "url": gist["html_url"],
            "html_url": gist["html_url"],
            "id": gist["id"],
            "filename": filename,
            "public": gist["public"],
        },
        pretty=False,
    )


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
