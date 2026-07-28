# Plan: add-publish-command

> **Goal:** Add `blackglass publish` CLI command that creates GitHub Gists from vault notes.
> **Architecture:** New `publish.py` module with pure functions for frontmatter stripping and date extraction, a GitHub API helper using httpx, and a Click command. Follows existing patterns (client.py for HTTP, _output.py for JSON emit).
> **Tech Stack:** Click, httpx (existing deps), pytest + respx (existing dev deps)

## Global Constraints

- Python >=3.12
- httpx for all HTTP (blackglass API + GitHub API)
- Follow existing code patterns: `_emit()` for output, `request()` for blackglass API, `sys.exit()` for errors
- All output to stdout is JSON (via `_emit` or `click.echo(json.dumps(...))`)
- All errors to stderr, then `sys.exit(N)`
- Tests use `runner` + `mock_api` fixtures from conftest.py; GitHub API mocked with respx

---

### Task 1: Frontmatter utilities

**Files:**
- Create: `src/blackglass_client/cli/publish.py`
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: none
- Produces: `strip_frontmatter(content: str) -> str`, `get_note_date(content: str) -> str`

- [ ] Step 1: Write failing tests for frontmatter utilities

```python
# tests/test_publish.py
from __future__ import annotations
from blackglass_client.cli.publish import strip_frontmatter, get_note_date


class TestStripFrontmatter:
    def test_strips_frontmatter(self):
        content = "---\ntags: [foo]\ndate: 2026-07-28\n---\n\n# Title\nBody"
        assert strip_frontmatter(content) == "# Title\nBody"

    def test_no_frontmatter(self):
        content = "# Title\nBody"
        assert strip_frontmatter(content) == "# Title\nBody"

    def test_empty_frontmatter(self):
        content = "---\n---\n\n# Title"
        assert strip_frontmatter(content) == "# Title"

    def test_frontmatter_with_dashes_in_body(self):
        content = "---\ntags: [foo]\n---\n\n# Title\n---\nMore content"
        result = strip_frontmatter(content)
        assert result == "# Title\n---\nMore content"


class TestGetNoteDate:
    def test_extracts_date(self):
        content = "---\ndate: 2026-07-28\ntags: [foo]\n---\nBody"
        assert get_note_date(content) == "2026-07-28"

    def test_no_date_returns_today(self):
        content = "---\ntags: [foo]\n---\nBody"
        result = get_note_date(content)
        # Should be today's date in YYYY-MM-DD format
        assert len(result) == 10
        assert result.count("-") == 2

    def test_no_frontmatter_returns_today(self):
        content = "# Title\nBody"
        result = get_note_date(content)
        assert len(result) == 10
```

- [ ] Step 2: Run tests to verify they fail

Run: `cd /home/fishhouses/Brian_Code/blackglass/blackglass-client && uv run pytest tests/test_publish.py -v`
Expected: FAIL (ModuleNotFoundError: cannot import 'strip_frontmatter')

- [ ] Step 3: Implement frontmatter utilities

```python
# src/blackglass_client/cli/publish.py
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
    # Find the closing ---
    lines = content.split("\n", 1)
    if len(lines) < 2:
        return content
    rest = lines[1]
    idx = rest.find("\n---\n")
    if idx == -1:
        # Try end-of-string variant
        if rest.rstrip().endswith("---"):
            return ""
        return content
    return rest[idx + 5:]  # skip "\n---\n"


def get_note_date(content: str) -> str:
    """Extract date from frontmatter, fall back to today."""
    if content.startswith("---"):
        lines = content.split("\n", 1)
        if len(lines) >= 2:
            match = re.search(r"^date:\s*(\d{4}-\d{2}-\d{2})", lines[1], re.MULTILINE)
            if match:
                return match.group(1)
    return date.today().isoformat()
```

- [ ] Step 4: Run tests to verify they pass

Run: `cd /home/fishhouses/Brian_Code/blackglass/blackglass-client && uv run pytest tests/test_publish.py -v`
Expected: PASS

- [ ] Step 5: Commit

```bash
cd /home/fishhouses/Brian_Code/blackglass/blackglass-client
git add src/blackglass_client/cli/publish.py tests/test_publish.py
git commit -m "feat(publish): add frontmatter stripping and date extraction"
```

---

### Task 2: GitHub gist creation

**Files:**
- Modify: `src/blackglass_client/cli/publish.py`
- Modify: `tests/test_publish.py`

**Interfaces:**
- Consumes: `GITHUB_PERSONAL_TOKEN` env var
- Produces: `create_gist(token: str, filename: str, content: str, description: str, public: bool) -> dict`

- [ ] Step 1: Write failing tests for gist creation

Append to `tests/test_publish.py`:

```python
import respx


class TestCreateGist:
    def test_creates_public_gist(self, monkeypatch):
        monkeypatch.setenv("GITHUB_PERSONAL_TOKEN", "ghp_test123")
        gist_response = {
            "url": "https://api.github.com/gists/abc123",
            "html_url": "https://gist.github.com/user/abc123",
            "id": "abc123",
            "public": True,
            "files": {"test.md": {"filename": "test.md"}},
        }
        with respx.mock(base_url="https://api.github.com") as github:
            route = github.post("/gists").respond(201, json=gist_response)
            from blackglass_client.cli.publish import create_gist
            result = create_gist("ghp_test123", "test.md", "# Content", "Test gist", True)
            assert result["id"] == "abc123"
            assert result["html_url"] == "https://gist.github.com/user/abc123"
            assert route.called
            sent = route.calls.last.request.content
            assert b'"public": true' in sent
            assert b'"# Content"' in sent

    def test_creates_private_gist(self, monkeypatch):
        monkeypatch.setenv("GITHUB_PERSONAL_TOKEN", "ghp_test123")
        gist_response = {
            "url": "https://api.github.com/gists/def456",
            "html_url": "https://gist.github.com/user/def456",
            "id": "def456",
            "public": False,
            "files": {"test.md": {"filename": "test.md"}},
        }
        with respx.mock(base_url="https://api.github.com") as github:
            route = github.post("/gists").respond(201, json=gist_response)
            from blackglass_client.cli.publish import create_gist
            result = create_gist("ghp_test123", "test.md", "# Content", "Test gist", False)
            assert result["public"] is False
            sent = route.calls.last.request.content
            assert b'"public": false' in sent
```

- [ ] Step 2: Run tests to verify they fail

Run: `cd /home/fishhouses/Brian_Code/blackglass/blackglass-client && uv run pytest tests/test_publish.py::TestCreateGist -v`
Expected: FAIL (ImportError: cannot import 'create_gist')

- [ ] Step 3: Implement create_gist

Append to `src/blackglass_client/cli/publish.py`:

```python
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
```

- [ ] Step 4: Run tests to verify they pass

Run: `cd /home/fishhouses/Brian_Code/blackglass/blackglass-client && uv run pytest tests/test_publish.py::TestCreateGist -v`
Expected: PASS

- [ ] Step 5: Commit

```bash
cd /home/fishhouses/Brian_Code/blackglass/blackglass-client
git add src/blackglass_client/cli/publish.py tests/test_publish.py
git commit -m "feat(publish): add GitHub gist creation via httpx"
```

---

### Task 3: Publish Click command

**Files:**
- Modify: `src/blackglass_client/cli/publish.py`
- Modify: `tests/test_publish.py`

**Interfaces:**
- Consumes: `strip_frontmatter()`, `get_note_date()`, `create_gist()` (from Tasks 1-2), `request()` from client.py
- Produces: `publish` Click command

- [ ] Step 1: Write failing tests for the publish command

Append to `tests/test_publish.py`:

```python
from click.testing import CliRunner
from blackglass_client.cli.main import cli


class TestPublishCommand:
    def test_publish_happy_path(self, runner, mock_api, monkeypatch):
        monkeypatch.setenv("GITHUB_PERSONAL_TOKEN", "ghp_test123")
        note_content = "---\ntags: [foo]\ndate: 2026-07-28\n---\n\n# My Note\nBody text"
        mock_api.get("/vault/notes/My%20Note.md").respond(
            200, json={"path": "My Note.md", "content": note_content}
        )
        gist_response = {
            "url": "https://api.github.com/gists/abc123",
            "html_url": "https://gist.github.com/user/abc123",
            "id": "abc123",
            "public": True,
            "files": {"My Note.md": {"filename": "My Note.md"}},
        }
        with respx.mock(base_url="https://api.github.com") as github:
            github.post("/gists").respond(201, json=gist_response)
            result = runner.invoke(cli, ["publish", "My Note.md"])
            assert result.exit_code == 0, result.stderr
            import json
            data = json.loads(result.stdout)
            assert data["html_url"] == "https://gist.github.com/user/abc123"
            assert data["id"] == "abc123"
            assert data["filename"] == "My Note.md"
            assert data["public"] is True

    def test_publish_private_flag(self, runner, mock_api, monkeypatch):
        monkeypatch.setenv("GITHUB_PERSONAL_TOKEN", "ghp_test123")
        mock_api.get("/vault/notes/foo.md").respond(
            200, json={"path": "foo.md", "content": "---\ndate: 2026-01-01\n---\nBody"}
        )
        gist_response = {
            "url": "https://api.github.com/gists/priv123",
            "html_url": "https://gist.github.com/user/priv123",
            "id": "priv123",
            "public": False,
            "files": {"foo.md": {"filename": "foo.md"}},
        }
        with respx.mock(base_url="https://api.github.com") as github:
            github.post("/gists").respond(201, json=gist_response)
            result = runner.invoke(cli, ["publish", "foo.md", "--private"])
            assert result.exit_code == 0, result.stderr
            import json
            data = json.loads(result.stdout)
            assert data["public"] is False

    def test_publish_missing_token(self, runner, mock_api, monkeypatch):
        monkeypatch.delenv("GITHUB_PERSONAL_TOKEN", raising=False)
        result = runner.invoke(cli, ["publish", "foo.md"])
        assert result.exit_code == 1
        assert "GITHUB_PERSONAL_TOKEN" in result.stderr

    def test_publish_note_not_found(self, runner, mock_api, monkeypatch):
        monkeypatch.setenv("GITHUB_PERSONAL_TOKEN", "ghp_test123")
        mock_api.get("/vault/notes/missing.md").respond(404, json={"detail": "Not found"})
        result = runner.invoke(cli, ["publish", "missing.md"])
        assert result.exit_code == 4
```

- [ ] Step 2: Run tests to verify they fail

Run: `cd /home/fishhouses/Brian_Code/blackglass/blackglass-client && uv run pytest tests/test_publish.py::TestPublishCommand -v`
Expected: FAIL (click.testing.CliRunner can't find 'publish' command)

- [ ] Step 3: Implement the publish command

Append to `src/blackglass_client/cli/publish.py` (before the `_GITHUB_BASE` line, or reorganize as needed):

```python
from .client import request
from ._output import _emit


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
            "id": gist["id"],
            "filename": filename,
            "public": gist["public"],
        },
        pretty=False,
    )
```

- [ ] Step 4: Run tests to verify they pass

Run: `cd /home/fishhouses/Brian_Code/blackglass/blackglass-client && uv run pytest tests/test_publish.py -v`
Expected: PASS

- [ ] Step 5: Commit

```bash
cd /home/fishhouses/Brian_Code/blackglass/blackglass-client
git add src/blackglass_client/cli/publish.py tests/test_publish.py
git commit -m "feat(publish): add Click command with full publish flow"
```

---

### Task 4: Register command in CLI

**Files:**
- Modify: `src/blackglass_client/cli/main.py`
- Modify: `tests/test_publish.py`

**Interfaces:**
- Consumes: `publish` command from publish.py
- Produces: `publish` visible in `blackglass --help`

- [ ] Step 1: Write test that publish appears in help

Append to `tests/test_publish.py`:

```python
class TestPublishRegistration:
    def test_publish_in_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "publish" in result.output

    def test_publish_help(self, runner):
        result = runner.invoke(cli, ["publish", "--help"])
        assert result.exit_code == 0
        assert "Publish a note as a GitHub Gist" in result.output
        assert "--private" in result.output
```

- [ ] Step 2: Run tests to verify they fail

Run: `cd /home/fishhouses/Brian_Code/blackglass/blackglass-client && uv run pytest tests/test_publish.py::TestPublishRegistration -v`
Expected: FAIL (assert "publish" in output — command not registered)

- [ ] Step 3: Register the command

Modify `src/blackglass_client/cli/main.py`:

```python
# Add import (line 4 area):
from .publish import publish

# Add registration (after cli.add_command(obs)):
cli.add_command(publish)
```

- [ ] Step 4: Run tests to verify they pass

Run: `cd /home/fishhouses/Brian_Code/blackglass/blackglass-client && uv run pytest tests/test_publish.py -v`
Expected: PASS

- [ ] Step 5: Commit

```bash
cd /home/fishhouses/Brian_Code/blackglass/blackglass-client
git add src/blackglass_client/cli/main.py tests/test_publish.py
git commit -m "feat(publish): register publish command in CLI group"
```

---

### Task 5: Update project.yaml

**Files:**
- Modify: `.sdd/add-publish-command/project.yaml`

- [ ] Step 1: Set phase to DONE

Update `.sdd/add-publish-command/project.yaml`:
- Set `phase: DONE`
- Set `task_index: null`
- Set `task_total: 5`

- [ ] Step 2: Commit

```bash
cd /home/fishhouses/Brian_Code/blackglass
git add .sdd/add-publish-command/project.yaml
git commit -m "chore(sdd): mark add-publish-command as DONE"
```
