# CLI Full Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the `blackglass-client` CLI to 100% endpoint and parameter fidelity with the `blackglass-server` HTTP API, with JSON-default output, structured stderr error envelopes, and a respx-backed test suite.

**Architecture:** Extend existing Click groups (`notes`, `vault`, `search`) and add a new `obs` group. Move HTTP error handling into `client.py` (envelope + `sys.exit`). Introduce two shared helper modules: `cli/_output.py` (`_emit`) and `cli/_payloads.py` (PATCH op builders). Drop `--json` flag in favor of JSON-default + global `--pretty`.

**Tech Stack:** Python 3.12+, Click, httpx, pytest, respx.

**Spec:** `docs/specs/2026-05-31-cli-full-coverage.md`

---

## File Structure

**New files:**
- `blackglass-client/src/blackglass_client/cli/_output.py`: `_emit()` JSON writer
- `blackglass-client/src/blackglass_client/cli/_payloads.py`: PATCH op body builders
- `blackglass-client/src/blackglass_client/cli/obs_cmds.py`: `obs` group with `status`, `logs-last`, `logs-journal`
- `blackglass-client/tests/__init__.py`: empty marker
- `blackglass-client/tests/conftest.py`: Click CliRunner + respx fixtures
- `blackglass-client/tests/test_helpers.py`: tests for `_output.py` and `_payloads.py`
- `blackglass-client/tests/test_client.py`: tests for `client.py` error envelope + exit codes
- `blackglass-client/tests/test_notes.py`: happy-path tests for all `notes` verbs
- `blackglass-client/tests/test_vault.py`: happy-path tests for base `vault` verbs (files, tags, backlinks, sync, changes)
- `blackglass-client/tests/test_periodic.py`: tests for `vault periodic` subgroup
- `blackglass-client/tests/test_search.py`: tests for all three search verbs
- `blackglass-client/tests/test_obs.py`: tests for `obs` group

**Modified files:**
- `blackglass-client/pyproject.toml`: add `[project.optional-dependencies] dev`
- `blackglass-client/src/blackglass_client/client.py`: error envelope + `sys.exit`
- `blackglass-client/src/blackglass_client/cli/main.py`: `--pretty` global flag, register `obs`
- `blackglass-client/src/blackglass_client/cli/notes.py`: full rewrite (drop `--json`, add `meta`/`prepend`/`replace`/`batch`/`move`)
- `blackglass-client/src/blackglass_client/cli/vault_cmds.py`: full rewrite (add filters, `changes`, `periodic` subgroup)
- `blackglass-client/src/blackglass_client/cli/search_cmds.py`: full rewrite (add `hybrid`, `--snippet-chars`)

---

## Task 1: Set up test scaffolding and dev dependencies

**Files:**
- Modify: `blackglass-client/pyproject.toml`
- Create: `blackglass-client/tests/__init__.py`
- Create: `blackglass-client/tests/conftest.py`

- [ ] **Step 1: Add dev extras to pyproject.toml**

Edit `blackglass-client/pyproject.toml`. After the `dependencies = [...]` block, add:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8",
    "respx>=0.21",
]
```

- [ ] **Step 2: Create empty tests package marker**

Create `blackglass-client/tests/__init__.py` with no content (empty file).

- [ ] **Step 3: Create conftest.py with shared fixtures**

Create `blackglass-client/tests/conftest.py`:

```python
from __future__ import annotations
import os
import pytest
import respx
from click.testing import CliRunner


BASE_URL = "http://test-server"
API_KEY = "test-key"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BLACKGLASS_URL", BASE_URL)
    monkeypatch.setenv("BLACKGLASS_API_KEY", API_KEY)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


@pytest.fixture
def mock_api():
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        yield router
```

- [ ] **Step 4: Install dev deps and verify pytest discovers tests**

Run from `blackglass-client/`:

```bash
uv pip install -e ".[dev]"
uv run pytest tests/ -v
```

Expected: `no tests ran` (zero tests collected). Exit code 5 is acceptable; exit code 0 with `no tests ran` is also acceptable.

- [ ] **Step 5: Commit**

```bash
git add blackglass-client/pyproject.toml blackglass-client/tests/__init__.py blackglass-client/tests/conftest.py
git commit -m "test(client): add pytest + respx scaffolding"
```

---

## Task 2: Build `_output.py` helper with tests

**Files:**
- Create: `blackglass-client/src/blackglass_client/cli/_output.py`
- Create: `blackglass-client/tests/test_helpers.py`

- [ ] **Step 1: Write failing test for `_emit`**

Create `blackglass-client/tests/test_helpers.py`:

```python
from __future__ import annotations
import json
import io
import click
from blackglass_client.cli._output import _emit


def _capture(fn) -> str:
    buf = io.StringIO()
    with click.Context(click.Command("x")):
        # Re-route click.echo through a buffer
        import click.utils
        orig = click.utils.echo
        try:
            click.utils.echo = lambda msg=None, **kw: buf.write((msg or "") + "\n")
            fn()
        finally:
            click.utils.echo = orig
    return buf.getvalue()


def test_emit_compact_default():
    out = _capture(lambda: _emit({"a": 1, "b": 2}, pretty=False))
    assert out == '{"a":1,"b":2}\n'


def test_emit_pretty():
    out = _capture(lambda: _emit({"a": 1}, pretty=True))
    assert out == '{\n  "a": 1\n}\n'


def test_emit_none_writes_nothing():
    out = _capture(lambda: _emit(None, pretty=False))
    assert out == ""


def test_emit_list():
    out = _capture(lambda: _emit([1, 2, 3], pretty=False))
    assert out == "[1,2,3]\n"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd blackglass-client && uv run pytest tests/test_helpers.py -v
```

Expected: ImportError / ModuleNotFoundError on `blackglass_client.cli._output`.

- [ ] **Step 3: Implement `_output.py`**

Create `blackglass-client/src/blackglass_client/cli/_output.py`:

```python
from __future__ import annotations
import json
import click


def _emit(data: dict | list | None, pretty: bool) -> None:
    if data is None:
        return
    if pretty:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(json.dumps(data, separators=(",", ":")))
```

- [ ] **Step 4: Run tests, verify pass**

```bash
cd blackglass-client && uv run pytest tests/test_helpers.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add blackglass-client/src/blackglass_client/cli/_output.py blackglass-client/tests/test_helpers.py
git commit -m "feat(client): add _emit JSON output helper"
```

---

## Task 3: Build `_payloads.py` PATCH op builders with tests

**Files:**
- Create: `blackglass-client/src/blackglass_client/cli/_payloads.py`
- Modify: `blackglass-client/tests/test_helpers.py`

- [ ] **Step 1: Append failing tests to test_helpers.py**

Append to `blackglass-client/tests/test_helpers.py`:

```python
from blackglass_client.cli._payloads import (
    patch_op_append,
    patch_op_prepend,
    patch_op_set_frontmatter,
    patch_op_replace,
)


def test_patch_op_append():
    assert patch_op_append("hello") == {"op": "append", "content": "hello"}


def test_patch_op_prepend():
    assert patch_op_prepend("hi") == {"op": "prepend", "content": "hi"}


def test_patch_op_set_frontmatter():
    assert patch_op_set_frontmatter("tag", "blue") == {
        "op": "set_frontmatter",
        "key": "tag",
        "value": "blue",
    }


def test_patch_op_replace_no_all():
    assert patch_op_replace("foo", "bar", False) == {
        "op": "replace",
        "old": "foo",
        "new": "bar",
        "replace_all": False,
    }


def test_patch_op_replace_all():
    assert patch_op_replace("foo", "bar", True) == {
        "op": "replace",
        "old": "foo",
        "new": "bar",
        "replace_all": True,
    }
```

- [ ] **Step 2: Run, verify fail**

```bash
cd blackglass-client && uv run pytest tests/test_helpers.py -v
```

Expected: ImportError on `blackglass_client.cli._payloads`.

- [ ] **Step 3: Implement `_payloads.py`**

Create `blackglass-client/src/blackglass_client/cli/_payloads.py`:

```python
from __future__ import annotations


def patch_op_append(content: str) -> dict:
    return {"op": "append", "content": content}


def patch_op_prepend(content: str) -> dict:
    return {"op": "prepend", "content": content}


def patch_op_set_frontmatter(key: str, value: str) -> dict:
    return {"op": "set_frontmatter", "key": key, "value": value}


def patch_op_replace(old: str, new: str, replace_all: bool) -> dict:
    return {"op": "replace", "old": old, "new": new, "replace_all": replace_all}
```

- [ ] **Step 4: Run, verify pass**

```bash
cd blackglass-client && uv run pytest tests/test_helpers.py -v
```

Expected: 9 passed total (4 from Task 2 + 5 new).

- [ ] **Step 5: Commit**

```bash
git add blackglass-client/src/blackglass_client/cli/_payloads.py blackglass-client/tests/test_helpers.py
git commit -m "feat(client): add PATCH op payload builders"
```

---

## Task 4: Rewrite `client.py` with error envelope and exit codes

**Files:**
- Modify: `blackglass-client/src/blackglass_client/client.py`
- Create: `blackglass-client/tests/test_client.py`

- [ ] **Step 1: Write failing tests for client error behavior**

Create `blackglass-client/tests/test_client.py`:

```python
from __future__ import annotations
import json
import sys
import httpx
import pytest
import respx
from blackglass_client.client import request


def test_request_success_returns_json(mock_api):
    mock_api.get("/vault/notes/foo.md").respond(200, json={"path": "foo.md", "content": "x"})
    result = request("GET", "/vault/notes/foo.md")
    assert result == {"path": "foo.md", "content": "x"}


def test_request_204_returns_none(mock_api):
    mock_api.delete("/vault/notes/foo.md").respond(204)
    result = request("DELETE", "/vault/notes/foo.md")
    assert result is None


def test_request_4xx_emits_envelope_and_exits_4(mock_api, capsys):
    mock_api.get("/vault/notes/missing.md").respond(404, json={"detail": "Note not found: missing.md"})
    with pytest.raises(SystemExit) as exc:
        request("GET", "/vault/notes/missing.md")
    assert exc.value.code == 4
    captured = capsys.readouterr()
    assert captured.out == ""
    envelope = json.loads(captured.err)
    assert envelope == {
        "error": "http_error",
        "status": 404,
        "method": "GET",
        "path": "/vault/notes/missing.md",
        "detail": "Note not found: missing.md",
    }


def test_request_5xx_exits_5(mock_api, capsys):
    mock_api.get("/vault/files").respond(500, json={"detail": "boom"})
    with pytest.raises(SystemExit) as exc:
        request("GET", "/vault/files")
    assert exc.value.code == 5
    envelope = json.loads(capsys.readouterr().err)
    assert envelope["error"] == "http_error"
    assert envelope["status"] == 500


def test_request_4xx_structured_detail_passthrough(mock_api, capsys):
    mock_api.patch("/vault/notes/x.md").respond(
        409,
        json={"detail": {"message": "old matched multiple times", "match_count": 3}},
    )
    with pytest.raises(SystemExit):
        request("PATCH", "/vault/notes/x.md", json={"op": "replace"})
    envelope = json.loads(capsys.readouterr().err)
    assert envelope["detail"] == {"message": "old matched multiple times", "match_count": 3}


def test_request_4xx_non_json_body(mock_api, capsys):
    mock_api.get("/vault/files").respond(400, content="not json", headers={"content-type": "text/plain"})
    with pytest.raises(SystemExit):
        request("GET", "/vault/files")
    envelope = json.loads(capsys.readouterr().err)
    assert envelope["detail"] == "not json"


def test_request_transport_error_exits_1(monkeypatch, capsys):
    def boom(*a, **kw):
        raise httpx.ConnectError("connection refused")
    monkeypatch.setattr(httpx.Client, "request", boom)
    with pytest.raises(SystemExit) as exc:
        request("GET", "/vault/files")
    assert exc.value.code == 1
    envelope = json.loads(capsys.readouterr().err)
    assert envelope["error"] == "transport_error"
    assert envelope["status"] is None
    assert "ConnectError" in envelope["detail"]
```

- [ ] **Step 2: Run, verify fail**

```bash
cd blackglass-client && uv run pytest tests/test_client.py -v
```

Expected: failures (current `client.py` raises `HTTPStatusError`, not `SystemExit`).

- [ ] **Step 3: Rewrite `client.py`**

Replace entire contents of `blackglass-client/src/blackglass_client/client.py`:

```python
from __future__ import annotations
import json
import os
import sys
import click
import httpx

_DEFAULT_URL = "http://172.16.0.3:8083"


def _client() -> httpx.Client:
    url = os.environ.get("BLACKGLASS_URL", _DEFAULT_URL)
    key = os.environ.get("BLACKGLASS_API_KEY", "")
    return httpx.Client(base_url=url, headers={"X-API-Key": key}, timeout=60.0)


def _extract_detail(resp: httpx.Response) -> object:
    try:
        body = resp.json()
    except ValueError:
        return resp.text
    if isinstance(body, dict) and "detail" in body:
        return body["detail"]
    return body


def request(method: str, path: str, **kwargs) -> dict | list | None:
    try:
        with _client() as c:
            resp = c.request(method, path, **kwargs)
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
    except httpx.HTTPStatusError as exc:
        envelope = {
            "error": "http_error",
            "status": exc.response.status_code,
            "method": method,
            "path": path,
            "detail": _extract_detail(exc.response),
        }
        click.echo(json.dumps(envelope), err=True)
        sys.exit(4 if 400 <= exc.response.status_code < 500 else 5)
    except httpx.RequestError as exc:
        envelope = {
            "error": "transport_error",
            "status": None,
            "method": method,
            "path": path,
            "detail": f"{type(exc).__name__}: {exc}",
        }
        click.echo(json.dumps(envelope), err=True)
        sys.exit(1)
```

- [ ] **Step 4: Run, verify pass**

```bash
cd blackglass-client && uv run pytest tests/test_client.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add blackglass-client/src/blackglass_client/client.py blackglass-client/tests/test_client.py
git commit -m "feat(client): route HTTP errors to stderr envelope + sys.exit"
```

---

## Task 5: Add `--pretty` global flag in `main.py`

**Files:**
- Modify: `blackglass-client/src/blackglass_client/cli/main.py`

- [ ] **Step 1: Rewrite main.py**

Replace contents of `blackglass-client/src/blackglass_client/cli/main.py`:

```python
from __future__ import annotations
import click
from .notes import notes
from .vault_cmds import vault
from .search_cmds import search
from .obs_cmds import obs


@click.group()
@click.option("--pretty", is_flag=True, help="Pretty-print JSON output (indent=2).")
@click.pass_context
def cli(ctx: click.Context, pretty: bool) -> None:
    """Blackglass: Obsidian vault over HTTP."""
    ctx.ensure_object(dict)
    ctx.obj["pretty"] = pretty


cli.add_command(notes)
cli.add_command(vault)
cli.add_command(search)
cli.add_command(obs)
```

Note: this references `obs_cmds.obs`, which doesn't exist yet. Task 9 creates it. Until then, `python -c "from blackglass_client.cli.main import cli"` will ImportError; that's expected. Don't commit yet; this task's commit waits until Task 9.

- [ ] **Step 2: Leave uncommitted**

No verification or commit in this task. Proceed to Task 6. The dangling import will be resolved in Task 9.

---

## Task 6: Rewrite `notes.py` with full verb set + tests

**Files:**
- Modify: `blackglass-client/src/blackglass_client/cli/notes.py`
- Create: `blackglass-client/tests/test_notes.py`

- [ ] **Step 1: Write failing tests for all `notes` verbs**

Create `blackglass-client/tests/test_notes.py`:

```python
from __future__ import annotations
import json
import httpx
from blackglass_client.cli.main import cli


def _ok(mock_api, method: str, path: str, body):
    return getattr(mock_api, method.lower())(path).respond(200, json=body)


def test_notes_get(runner, mock_api):
    route = mock_api.get("/vault/notes/foo.md").respond(200, json={"path": "foo.md", "content": "hi"})
    result = runner.invoke(cli, ["notes", "get", "foo.md"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {"path": "foo.md", "content": "hi"}
    assert route.called


def test_notes_meta(runner, mock_api):
    route = mock_api.get("/vault/notes/foo.md/meta").respond(200, json={"path": "foo.md", "size": 10})
    result = runner.invoke(cli, ["notes", "meta", "foo.md"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"path": "foo.md", "size": 10}
    assert route.called


def test_notes_create(runner, mock_api):
    route = mock_api.post("/vault/notes").respond(201, json={"path": "new.md", "content": "x"})
    result = runner.invoke(cli, ["notes", "create", "new.md", "--content", "x"])
    assert result.exit_code == 0
    assert route.called
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"content": "x"}
    assert route.calls.last.request.url.params["path"] == "new.md"


def test_notes_update(runner, mock_api):
    route = mock_api.put("/vault/notes/foo.md").respond(200, json={"path": "foo.md", "content": "new"})
    result = runner.invoke(cli, ["notes", "update", "foo.md", "--content", "new"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"content": "new"}


def test_notes_append(runner, mock_api):
    route = mock_api.patch("/vault/notes/foo.md").respond(200, json={"path": "foo.md", "content": "a\nb"})
    result = runner.invoke(cli, ["notes", "append", "foo.md", "b"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"op": "append", "content": "b"}


def test_notes_prepend(runner, mock_api):
    route = mock_api.patch("/vault/notes/foo.md").respond(200, json={"path": "foo.md"})
    result = runner.invoke(cli, ["notes", "prepend", "foo.md", "intro"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"op": "prepend", "content": "intro"}


def test_notes_set_frontmatter(runner, mock_api):
    route = mock_api.patch("/vault/notes/foo.md").respond(200, json={"path": "foo.md"})
    result = runner.invoke(cli, ["notes", "set-frontmatter", "foo.md", "tag", "blue"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {
        "op": "set_frontmatter",
        "key": "tag",
        "value": "blue",
    }


def test_notes_replace(runner, mock_api):
    route = mock_api.patch("/vault/notes/foo.md").respond(200, json={"path": "foo.md"})
    result = runner.invoke(cli, ["notes", "replace", "foo.md", "--old", "x", "--new", "y"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {
        "op": "replace",
        "old": "x",
        "new": "y",
        "replace_all": False,
    }


def test_notes_replace_all(runner, mock_api):
    route = mock_api.patch("/vault/notes/foo.md").respond(200, json={"path": "foo.md"})
    result = runner.invoke(
        cli, ["notes", "replace", "foo.md", "--old", "x", "--new", "y", "--replace-all"]
    )
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content)["replace_all"] is True


def test_notes_delete(runner, mock_api):
    route = mock_api.delete("/vault/notes/foo.md").respond(204)
    result = runner.invoke(cli, ["notes", "delete", "foo.md"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert route.called


def test_notes_batch_positional(runner, mock_api):
    route = mock_api.post("/vault/notes/batch").respond(200, json={"results": [], "summary": {}})
    result = runner.invoke(cli, ["notes", "batch", "a.md", "b.md"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"paths": ["a.md", "b.md"]}


def test_notes_batch_stdin(runner, mock_api):
    route = mock_api.post("/vault/notes/batch").respond(200, json={"results": [], "summary": {}})
    result = runner.invoke(cli, ["notes", "batch", "--stdin"], input="a.md\nb.md\n")
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"paths": ["a.md", "b.md"]}


def test_notes_batch_both_is_usage_error(runner, mock_api):
    result = runner.invoke(cli, ["notes", "batch", "--stdin", "a.md"])
    assert result.exit_code == 2


def test_notes_move(runner, mock_api):
    route = mock_api.post("/vault/notes/old.md/move").respond(200, json={"from": "old.md", "to": "new.md"})
    result = runner.invoke(cli, ["notes", "move", "old.md", "new.md"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"to": "new.md", "rewrite_links": True}


def test_notes_move_no_rewrite(runner, mock_api):
    route = mock_api.post("/vault/notes/old.md/move").respond(200, json={"from": "old.md", "to": "new.md"})
    result = runner.invoke(cli, ["notes", "move", "old.md", "new.md", "--no-rewrite-links"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"to": "new.md", "rewrite_links": False}


def test_pretty_flag(runner, mock_api):
    mock_api.get("/vault/notes/foo.md").respond(200, json={"a": 1})
    result = runner.invoke(cli, ["--pretty", "notes", "get", "foo.md"])
    assert result.exit_code == 0
    assert result.stdout == '{\n  "a": 1\n}\n'
```

- [ ] **Step 2: Run, verify fail**

```bash
cd blackglass-client && uv run pytest tests/test_notes.py -v
```

Expected: ImportError on `obs_cmds`, or `notes get` returns the old `--json`-shaped output and doesn't match the expected raw JSON. Both classes of failure are acceptable here; we're about to fix both.

- [ ] **Step 3: Rewrite `notes.py`**

Replace contents of `blackglass-client/src/blackglass_client/cli/notes.py`:

```python
from __future__ import annotations
import sys
import click
from ..client import request
from ._output import _emit
from ._payloads import (
    patch_op_append,
    patch_op_prepend,
    patch_op_set_frontmatter,
    patch_op_replace,
)


@click.group()
def notes():
    """Note CRUD operations."""


@notes.command("get")
@click.argument("path")
@click.pass_context
def get_note(ctx: click.Context, path: str) -> None:
    """Get a note by vault-relative path."""
    _emit(request("GET", f"/vault/notes/{path}"), ctx.obj["pretty"])


@notes.command("meta")
@click.argument("path")
@click.pass_context
def note_meta(ctx: click.Context, path: str) -> None:
    """Get note metadata (size, mtime, frontmatter)."""
    _emit(request("GET", f"/vault/notes/{path}/meta"), ctx.obj["pretty"])


@notes.command("create")
@click.argument("path")
@click.option("--content", required=True, help="Note content (markdown).")
@click.pass_context
def create_note(ctx: click.Context, path: str, content: str) -> None:
    """Create a new note."""
    _emit(
        request("POST", "/vault/notes", params={"path": path}, json={"content": content}),
        ctx.obj["pretty"],
    )


@notes.command("update")
@click.argument("path")
@click.option("--content", required=True)
@click.pass_context
def update_note(ctx: click.Context, path: str, content: str) -> None:
    """Replace a note's content."""
    _emit(
        request("PUT", f"/vault/notes/{path}", json={"content": content}),
        ctx.obj["pretty"],
    )


@notes.command("append")
@click.argument("path")
@click.argument("content")
@click.pass_context
def append_note(ctx: click.Context, path: str, content: str) -> None:
    """Append content to a note."""
    _emit(
        request("PATCH", f"/vault/notes/{path}", json=patch_op_append(content)),
        ctx.obj["pretty"],
    )


@notes.command("prepend")
@click.argument("path")
@click.argument("content")
@click.pass_context
def prepend_note(ctx: click.Context, path: str, content: str) -> None:
    """Prepend content to a note (after frontmatter)."""
    _emit(
        request("PATCH", f"/vault/notes/{path}", json=patch_op_prepend(content)),
        ctx.obj["pretty"],
    )


@notes.command("set-frontmatter")
@click.argument("path")
@click.argument("key")
@click.argument("value")
@click.pass_context
def set_frontmatter(ctx: click.Context, path: str, key: str, value: str) -> None:
    """Set a frontmatter field on a note."""
    _emit(
        request("PATCH", f"/vault/notes/{path}", json=patch_op_set_frontmatter(key, value)),
        ctx.obj["pretty"],
    )


@notes.command("replace")
@click.argument("path")
@click.option("--old", required=True, help="Anchor string to replace.")
@click.option("--new", required=True, help="Replacement string.")
@click.option("--replace-all", is_flag=True, help="Replace all occurrences (default: first only).")
@click.pass_context
def replace_note(ctx: click.Context, path: str, old: str, new: str, replace_all: bool) -> None:
    """Anchored find-and-replace in a note."""
    _emit(
        request(
            "PATCH",
            f"/vault/notes/{path}",
            json=patch_op_replace(old, new, replace_all),
        ),
        ctx.obj["pretty"],
    )


@notes.command("delete")
@click.argument("path")
def delete_note(path: str) -> None:
    """Delete a note."""
    request("DELETE", f"/vault/notes/{path}")


@notes.command("batch")
@click.argument("paths", nargs=-1)
@click.option("--stdin", "from_stdin", is_flag=True, help="Read newline-separated paths from stdin.")
@click.pass_context
def batch_read(ctx: click.Context, paths: tuple[str, ...], from_stdin: bool) -> None:
    """Batch-read multiple notes in one request (max 50)."""
    if from_stdin and paths:
        raise click.UsageError("--stdin and positional paths are mutually exclusive")
    if from_stdin:
        path_list = [line for line in sys.stdin.read().splitlines() if line]
    else:
        path_list = list(paths)
    _emit(
        request("POST", "/vault/notes/batch", json={"paths": path_list}),
        ctx.obj["pretty"],
    )


@notes.command("move")
@click.argument("src")
@click.argument("dst")
@click.option(
    "--rewrite-links/--no-rewrite-links",
    default=True,
    help="Rewrite wikilinks pointing to SRC (default: yes).",
)
@click.pass_context
def move_note(ctx: click.Context, src: str, dst: str, rewrite_links: bool) -> None:
    """Move/rename a note. Rewrites wikilinks by default."""
    _emit(
        request(
            "POST",
            f"/vault/notes/{src}/move",
            json={"to": dst, "rewrite_links": rewrite_links},
        ),
        ctx.obj["pretty"],
    )
```

- [ ] **Step 4: Still cannot run tests (main.py imports obs_cmds which doesn't exist)**

Skip verification for this task; tests will run after Task 9. Do not commit yet.

---

## Task 7: Rewrite `vault_cmds.py` base verbs + tests

**Files:**
- Modify: `blackglass-client/src/blackglass_client/cli/vault_cmds.py`
- Create: `blackglass-client/tests/test_vault.py`

- [ ] **Step 1: Write failing tests for base vault verbs**

Create `blackglass-client/tests/test_vault.py`:

```python
from __future__ import annotations
import json
from blackglass_client.cli.main import cli


def test_vault_files_no_filters(runner, mock_api):
    route = mock_api.get("/vault/files").respond(200, json=["a.md", "b.md"])
    result = runner.invoke(cli, ["vault", "files"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == ["a.md", "b.md"]
    assert route.called
    assert str(route.calls.last.request.url) == "http://test-server/vault/files"


def test_vault_files_with_tags(runner, mock_api):
    mock_api.get("/vault/files").respond(200, json={"files": [], "total": 0, "filtered_from": 0})
    result = runner.invoke(
        cli, ["vault", "files", "--tag", "foo", "--tag", "bar", "--limit", "5"]
    )
    assert result.exit_code == 0
    qs = mock_api.calls.last.request.url.params
    assert qs.get_list("tag") == ["foo", "bar"]
    assert qs["limit"] == "5"


def test_vault_files_with_fm(runner, mock_api):
    mock_api.get("/vault/files").respond(200, json={"files": [], "total": 0, "filtered_from": 0})
    result = runner.invoke(
        cli, ["vault", "files", "--fm", "status=draft", "--fm", "type=note"]
    )
    assert result.exit_code == 0
    qs = mock_api.calls.last.request.url.params
    assert qs["fm.status"] == "draft"
    assert qs["fm.type"] == "note"


def test_vault_files_with_path_glob(runner, mock_api):
    mock_api.get("/vault/files").respond(200, json={"files": [], "total": 0, "filtered_from": 0})
    result = runner.invoke(cli, ["vault", "files", "--path-glob", "Daily/*.md"])
    assert result.exit_code == 0
    assert mock_api.calls.last.request.url.params["path_glob"] == "Daily/*.md"


def test_vault_files_bad_fm_format(runner, mock_api):
    result = runner.invoke(cli, ["vault", "files", "--fm", "no-equals-sign"])
    assert result.exit_code == 2


def test_vault_tags(runner, mock_api):
    route = mock_api.get("/vault/tags").respond(200, json=[{"tag": "blue", "count": 3}])
    result = runner.invoke(cli, ["vault", "tags"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == [{"tag": "blue", "count": 3}]


def test_vault_backlinks(runner, mock_api):
    route = mock_api.get("/vault/backlinks/foo.md").respond(
        200, json={"path": "foo.md", "backlinks": ["bar.md"]}
    )
    result = runner.invoke(cli, ["vault", "backlinks", "foo.md"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"path": "foo.md", "backlinks": ["bar.md"]}


def test_vault_sync(runner, mock_api):
    route = mock_api.post("/vault/sync").respond(
        200, json={"git": "ok", "files_checked": 100, "files_indexed": 4}
    )
    result = runner.invoke(cli, ["vault", "sync"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"git": "ok", "files_checked": 100, "files_indexed": 4}


def test_vault_changes_default(runner, mock_api):
    route = mock_api.get("/vault/changes").respond(200, json={"since": 0, "limit": 200, "changes": [], "truncated": False})
    result = runner.invoke(cli, ["vault", "changes"])
    assert result.exit_code == 0
    assert route.called
    assert dict(mock_api.calls.last.request.url.params) == {}


def test_vault_changes_with_days(runner, mock_api):
    mock_api.get("/vault/changes").respond(200, json={"since": 0, "limit": 10, "changes": [], "truncated": False})
    result = runner.invoke(cli, ["vault", "changes", "--days", "3", "--limit", "10", "--diff-stats"])
    assert result.exit_code == 0
    qs = mock_api.calls.last.request.url.params
    assert qs["days"] == "3"
    assert qs["limit"] == "10"
    assert qs["include_diff_stats"] == "true"


def test_vault_changes_with_since(runner, mock_api):
    mock_api.get("/vault/changes").respond(200, json={"since": 0, "limit": 200, "changes": [], "truncated": False})
    result = runner.invoke(cli, ["vault", "changes", "--since", "1700000000"])
    assert result.exit_code == 0
    assert mock_api.calls.last.request.url.params["since"] == "1700000000"
```

- [ ] **Step 2: Rewrite the base portion of `vault_cmds.py`**

Replace contents of `blackglass-client/src/blackglass_client/cli/vault_cmds.py`:

```python
from __future__ import annotations
import click
from ..client import request
from ._output import _emit
from ._payloads import (
    patch_op_append,
    patch_op_prepend,
    patch_op_set_frontmatter,
    patch_op_replace,
)


@click.group()
def vault():
    """Vault-level operations."""


def _parse_fm(ctx: click.Context, param: click.Parameter, values: tuple[str, ...]) -> dict:
    out: dict[str, str] = {}
    for v in values:
        if "=" not in v:
            raise click.BadParameter(f"--fm expects KEY=VALUE, got: {v!r}")
        k, val = v.split("=", 1)
        out[k] = val
    return out


@vault.command("files")
@click.option("--tag", multiple=True, help="Filter to notes tagged with TAG. Repeatable.")
@click.option(
    "--fm",
    "fm_filters",
    multiple=True,
    callback=_parse_fm,
    help="Filter by frontmatter KEY=VALUE. Repeatable.",
)
@click.option("--path-glob", help="POSIX glob to restrict paths.")
@click.option("--limit", type=int, help="Cap result count.")
@click.pass_context
def files(
    ctx: click.Context,
    tag: tuple[str, ...],
    fm_filters: dict[str, str],
    path_glob: str | None,
    limit: int | None,
) -> None:
    """List notes in the vault, optionally filtered."""
    params: list[tuple[str, str]] = []
    for t in tag:
        params.append(("tag", t))
    for k, v in fm_filters.items():
        params.append((f"fm.{k}", v))
    if path_glob is not None:
        params.append(("path_glob", path_glob))
    if limit is not None:
        params.append(("limit", str(limit)))
    _emit(request("GET", "/vault/files", params=params), ctx.obj["pretty"])


@vault.command("tags")
@click.pass_context
def tags(ctx: click.Context) -> None:
    """List all tags with counts."""
    _emit(request("GET", "/vault/tags"), ctx.obj["pretty"])


@vault.command("backlinks")
@click.argument("path")
@click.pass_context
def backlinks(ctx: click.Context, path: str) -> None:
    """List notes that link to PATH."""
    _emit(request("GET", f"/vault/backlinks/{path}"), ctx.obj["pretty"])


@vault.command("sync")
@click.pass_context
def sync(ctx: click.Context) -> None:
    """Git pull and re-index changed notes."""
    _emit(request("POST", "/vault/sync"), ctx.obj["pretty"])


@vault.command("changes")
@click.option("--since", help="Epoch seconds or ISO 8601 timestamp.")
@click.option("--days", type=int, help="Look back N days (1..365).")
@click.option("--limit", type=int, help="Cap returned changes (1..2000, default 200).")
@click.option("--diff-stats", is_flag=True, help="Include per-file diff stats.")
@click.pass_context
def changes(
    ctx: click.Context,
    since: str | None,
    days: int | None,
    limit: int | None,
    diff_stats: bool,
) -> None:
    """List recent vault changes from git history."""
    params: dict[str, str] = {}
    if since is not None:
        params["since"] = since
    if days is not None:
        params["days"] = str(days)
    if limit is not None:
        params["limit"] = str(limit)
    if diff_stats:
        params["include_diff_stats"] = "true"
    _emit(request("GET", "/vault/changes", params=params or None), ctx.obj["pretty"])


# Periodic subgroup is registered in Task 8.
```

- [ ] **Step 3: Defer test run**

Tests still cannot run because `obs_cmds.py` is missing. Skip verification. Proceed to Task 8.

---

## Task 8: Add `vault periodic` subgroup + tests

**Files:**
- Modify: `blackglass-client/src/blackglass_client/cli/vault_cmds.py`
- Create: `blackglass-client/tests/test_periodic.py`

- [ ] **Step 1: Write tests for periodic subgroup**

Create `blackglass-client/tests/test_periodic.py`:

```python
from __future__ import annotations
import json
from blackglass_client.cli.main import cli


def test_periodic_list(runner, mock_api):
    route = mock_api.get("/vault/periodic").respond(200, json=[{"path": "2026-05-30.md"}])
    result = runner.invoke(cli, ["vault", "periodic", "list"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == [{"path": "2026-05-30.md"}]
    assert route.called


def test_periodic_today(runner, mock_api):
    route = mock_api.get("/vault/periodic/today").respond(200, json={"path": "today.md", "created": True})
    result = runner.invoke(cli, ["vault", "periodic", "today"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"path": "today.md", "created": True}


def test_periodic_yesterday(runner, mock_api):
    route = mock_api.get("/vault/periodic/yesterday").respond(200, json={"path": "yesterday.md", "created": False})
    result = runner.invoke(cli, ["vault", "periodic", "yesterday"])
    assert result.exit_code == 0
    assert route.called


def test_periodic_on(runner, mock_api):
    route = mock_api.get("/vault/periodic/by-date/2026-05-31").respond(200, json={"path": "2026-05-31.md", "created": False})
    result = runner.invoke(cli, ["vault", "periodic", "on", "2026-05-31"])
    assert result.exit_code == 0
    assert route.called


def test_periodic_append_today(runner, mock_api):
    route = mock_api.post("/vault/periodic/today/append").respond(200, json={"path": "today.md"})
    result = runner.invoke(cli, ["vault", "periodic", "append-today", "more stuff"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"content": "more stuff"}


def test_periodic_patch_today_append(runner, mock_api):
    route = mock_api.patch("/vault/periodic/today").respond(200, json={"path": "today.md"})
    result = runner.invoke(cli, ["vault", "periodic", "patch-today", "append", "hello"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"op": "append", "content": "hello"}


def test_periodic_patch_today_prepend(runner, mock_api):
    route = mock_api.patch("/vault/periodic/today").respond(200, json={"path": "today.md"})
    result = runner.invoke(cli, ["vault", "periodic", "patch-today", "prepend", "hi"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"op": "prepend", "content": "hi"}


def test_periodic_patch_today_set_frontmatter(runner, mock_api):
    route = mock_api.patch("/vault/periodic/today").respond(200, json={"path": "today.md"})
    result = runner.invoke(
        cli, ["vault", "periodic", "patch-today", "set-frontmatter", "mood", "great"]
    )
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {
        "op": "set_frontmatter",
        "key": "mood",
        "value": "great",
    }


def test_periodic_patch_today_replace(runner, mock_api):
    route = mock_api.patch("/vault/periodic/today").respond(200, json={"path": "today.md"})
    result = runner.invoke(
        cli, ["vault", "periodic", "patch-today", "replace", "--old", "x", "--new", "y"]
    )
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {
        "op": "replace",
        "old": "x",
        "new": "y",
        "replace_all": False,
    }
```

- [ ] **Step 2: Append periodic subgroup to `vault_cmds.py`**

Append to `blackglass-client/src/blackglass_client/cli/vault_cmds.py` (replacing the `# Periodic subgroup is registered in Task 8.` marker):

```python
@vault.group("periodic")
def periodic():
    """Daily/periodic note operations."""


@periodic.command("list")
@click.pass_context
def periodic_list(ctx: click.Context) -> None:
    """List all periodic (daily) notes."""
    _emit(request("GET", "/vault/periodic"), ctx.obj["pretty"])


@periodic.command("today")
@click.pass_context
def periodic_today(ctx: click.Context) -> None:
    """Get (and ensure) today's daily note."""
    _emit(request("GET", "/vault/periodic/today"), ctx.obj["pretty"])


@periodic.command("yesterday")
@click.pass_context
def periodic_yesterday(ctx: click.Context) -> None:
    """Get (and ensure) yesterday's daily note."""
    _emit(request("GET", "/vault/periodic/yesterday"), ctx.obj["pretty"])


@periodic.command("on")
@click.argument("date_str")
@click.pass_context
def periodic_on(ctx: click.Context, date_str: str) -> None:
    """Get (and ensure) the daily note for DATE_STR (YYYY-MM-DD)."""
    _emit(request("GET", f"/vault/periodic/by-date/{date_str}"), ctx.obj["pretty"])


@periodic.command("append-today")
@click.argument("content")
@click.pass_context
def periodic_append_today(ctx: click.Context, content: str) -> None:
    """Append CONTENT to today's daily note."""
    _emit(
        request("POST", "/vault/periodic/today/append", json={"content": content}),
        ctx.obj["pretty"],
    )


@periodic.group("patch-today")
def patch_today():
    """Patch today's daily note (op subcommands)."""


def _patch_today_send(ctx: click.Context, body: dict) -> None:
    _emit(request("PATCH", "/vault/periodic/today", json=body), ctx.obj["pretty"])


@patch_today.command("append")
@click.argument("content")
@click.pass_context
def patch_today_append(ctx: click.Context, content: str) -> None:
    _patch_today_send(ctx, patch_op_append(content))


@patch_today.command("prepend")
@click.argument("content")
@click.pass_context
def patch_today_prepend(ctx: click.Context, content: str) -> None:
    _patch_today_send(ctx, patch_op_prepend(content))


@patch_today.command("set-frontmatter")
@click.argument("key")
@click.argument("value")
@click.pass_context
def patch_today_set_frontmatter(ctx: click.Context, key: str, value: str) -> None:
    _patch_today_send(ctx, patch_op_set_frontmatter(key, value))


@patch_today.command("replace")
@click.option("--old", required=True)
@click.option("--new", required=True)
@click.option("--replace-all", is_flag=True)
@click.pass_context
def patch_today_replace(ctx: click.Context, old: str, new: str, replace_all: bool) -> None:
    _patch_today_send(ctx, patch_op_replace(old, new, replace_all))
```

- [ ] **Step 3: Defer test run**

Tests still cannot run; `obs_cmds.py` missing. Proceed to Task 9.

---

## Task 9: Add `obs_cmds.py` + tests; full test suite passes

**Files:**
- Create: `blackglass-client/src/blackglass_client/cli/obs_cmds.py`
- Create: `blackglass-client/tests/test_obs.py`

- [ ] **Step 1: Write tests for obs verbs**

Create `blackglass-client/tests/test_obs.py`:

```python
from __future__ import annotations
import json
from blackglass_client.cli.main import cli


def test_obs_status(runner, mock_api):
    route = mock_api.get("/status").respond(200, json={"name": "blackglass", "version": "0.1.0"})
    result = runner.invoke(cli, ["obs", "status"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {"name": "blackglass", "version": "0.1.0"}


def test_obs_logs_last_default(runner, mock_api):
    route = mock_api.get("/logs/last").respond(200, json={"entries": [], "total_buffered": 0, "capacity": 1000})
    result = runner.invoke(cli, ["obs", "logs-last"])
    assert result.exit_code == 0
    assert dict(mock_api.calls.last.request.url.params) == {}


def test_obs_logs_last_with_n(runner, mock_api):
    mock_api.get("/logs/last").respond(200, json={"entries": [], "total_buffered": 0, "capacity": 1000})
    result = runner.invoke(cli, ["obs", "logs-last", "-n", "25"])
    assert result.exit_code == 0
    assert mock_api.calls.last.request.url.params["n"] == "25"


def test_obs_logs_journal_default(runner, mock_api):
    route = mock_api.get("/logs/journal").respond(200, json={"unit": "blackglass", "n_requested": 100, "lines": []})
    result = runner.invoke(cli, ["obs", "logs-journal"])
    assert result.exit_code == 0


def test_obs_logs_journal_with_n(runner, mock_api):
    mock_api.get("/logs/journal").respond(200, json={"unit": "blackglass", "n_requested": 200, "lines": []})
    result = runner.invoke(cli, ["obs", "logs-journal", "-n", "200"])
    assert result.exit_code == 0
    assert mock_api.calls.last.request.url.params["n"] == "200"
```

- [ ] **Step 2: Implement `obs_cmds.py`**

Create `blackglass-client/src/blackglass_client/cli/obs_cmds.py`:

```python
from __future__ import annotations
import click
from ..client import request
from ._output import _emit


@click.group()
def obs():
    """Observability: status and logs."""


@obs.command("status")
@click.pass_context
def status(ctx: click.Context) -> None:
    """Server status, version, indexed count, last sync."""
    _emit(request("GET", "/status"), ctx.obj["pretty"])


@obs.command("logs-last")
@click.option("-n", "n", type=int, help="Number of entries (1..200, default 50).")
@click.pass_context
def logs_last(ctx: click.Context, n: int | None) -> None:
    """In-memory ring buffer of recent log records."""
    params = {"n": str(n)} if n is not None else None
    _emit(request("GET", "/logs/last", params=params), ctx.obj["pretty"])


@obs.command("logs-journal")
@click.option("-n", "n", type=int, help="Number of lines (1..2000, default 100).")
@click.pass_context
def logs_journal(ctx: click.Context, n: int | None) -> None:
    """systemd journal entries for the blackglass unit."""
    params = {"n": str(n)} if n is not None else None
    _emit(request("GET", "/logs/journal", params=params), ctx.obj["pretty"])
```

- [ ] **Step 3: Run full test suite**

```bash
cd blackglass-client && uv run pytest tests/ -v
```

Expected: all tests pass. Approximate counts:
- test_helpers.py: 9
- test_client.py: 7
- test_notes.py: 16
- test_vault.py: 11
- test_periodic.py: 9
- test_obs.py: 5
- Total: ~57

If any fail, fix inline before committing.

- [ ] **Step 4: Commit all changes from Tasks 5-9 together**

```bash
git add blackglass-client/src/blackglass_client/cli/main.py \
        blackglass-client/src/blackglass_client/cli/notes.py \
        blackglass-client/src/blackglass_client/cli/vault_cmds.py \
        blackglass-client/src/blackglass_client/cli/obs_cmds.py \
        blackglass-client/tests/test_notes.py \
        blackglass-client/tests/test_vault.py \
        blackglass-client/tests/test_periodic.py \
        blackglass-client/tests/test_obs.py
git commit -m "feat(client): full CLI coverage of server endpoints

- Adds notes meta/prepend/replace/batch/move
- Adds vault changes; expands files with tag/fm/path-glob/limit
- Adds vault periodic subgroup (list/today/yesterday/on/append-today/patch-today)
- Adds search hybrid; --snippet-chars on text/semantic/hybrid (in next commit)
- Adds obs group: status/logs-last/logs-journal
- Drops per-command --json; JSON is default; global --pretty for humans
- Routes HTTP errors to stderr envelope + exit 4/5; transport errors exit 1

Spec: docs/specs/2026-05-31-cli-full-coverage.md"
```

Note: `search_cmds.py` is updated in Task 10 and committed separately.

---

## Task 10: Rewrite `search_cmds.py` with hybrid + snippet-chars + tests

**Files:**
- Modify: `blackglass-client/src/blackglass_client/cli/search_cmds.py`
- Create: `blackglass-client/tests/test_search.py`

- [ ] **Step 1: Write tests for search verbs**

Create `blackglass-client/tests/test_search.py`:

```python
from __future__ import annotations
import json
from blackglass_client.cli.main import cli


def test_search_text(runner, mock_api):
    route = mock_api.get("/vault/search").respond(200, json=[{"path": "a.md", "score": 1.0}])
    result = runner.invoke(cli, ["search", "text", "hello"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == [{"path": "a.md", "score": 1.0}]
    qs = mock_api.calls.last.request.url.params
    assert qs["q"] == "hello"
    assert "snippet_chars" not in qs


def test_search_text_snippet_chars(runner, mock_api):
    mock_api.get("/vault/search").respond(200, json=[])
    result = runner.invoke(cli, ["search", "text", "hello", "--snippet-chars", "500"])
    assert result.exit_code == 0
    assert mock_api.calls.last.request.url.params["snippet_chars"] == "500"


def test_search_semantic(runner, mock_api):
    route = mock_api.get("/vault/semantic-search").respond(200, json=[{"path": "a.md"}])
    result = runner.invoke(cli, ["search", "semantic", "vector query"])
    assert result.exit_code == 0
    assert mock_api.calls.last.request.url.params["q"] == "vector query"


def test_search_semantic_limit(runner, mock_api):
    mock_api.get("/vault/semantic-search").respond(200, json=[])
    result = runner.invoke(
        cli, ["search", "semantic", "x", "--limit", "5", "--snippet-chars", "200"]
    )
    assert result.exit_code == 0
    qs = mock_api.calls.last.request.url.params
    assert qs["limit"] == "5"
    assert qs["snippet_chars"] == "200"


def test_search_hybrid(runner, mock_api):
    route = mock_api.get("/vault/hybrid-search").respond(
        200, json={"results": [{"path": "a.md", "score": 0.5}], "degraded": None}
    )
    result = runner.invoke(cli, ["search", "hybrid", "x"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"results": [{"path": "a.md", "score": 0.5}], "degraded": None}


def test_search_hybrid_all_params(runner, mock_api):
    mock_api.get("/vault/hybrid-search").respond(
        200, json={"results": [], "degraded": None}
    )
    result = runner.invoke(
        cli,
        ["search", "hybrid", "x", "--limit", "20", "--snippet-chars", "0", "--k", "30"],
    )
    assert result.exit_code == 0
    qs = mock_api.calls.last.request.url.params
    assert qs["limit"] == "20"
    assert qs["snippet_chars"] == "0"
    assert qs["k"] == "30"
```

- [ ] **Step 2: Rewrite `search_cmds.py`**

Replace contents of `blackglass-client/src/blackglass_client/cli/search_cmds.py`:

```python
from __future__ import annotations
import click
from ..client import request
from ._output import _emit


@click.group()
def search():
    """Search the vault."""


@search.command("text")
@click.argument("query")
@click.option("--snippet-chars", type=int, help="Snippet length per hit (0..1000, default 300).")
@click.pass_context
def text_search(ctx: click.Context, query: str, snippet_chars: int | None) -> None:
    """Full-text search across all notes."""
    params: dict[str, str] = {"q": query}
    if snippet_chars is not None:
        params["snippet_chars"] = str(snippet_chars)
    _emit(request("GET", "/vault/search", params=params), ctx.obj["pretty"])


@search.command("semantic")
@click.argument("query")
@click.option("--limit", type=int, help="Result cap (1..100, default 10).")
@click.option("--snippet-chars", type=int, help="Snippet length per hit (0..1000, default 300).")
@click.pass_context
def semantic_search(
    ctx: click.Context, query: str, limit: int | None, snippet_chars: int | None
) -> None:
    """Semantic (embedding) search across indexed notes."""
    params: dict[str, str] = {"q": query}
    if limit is not None:
        params["limit"] = str(limit)
    if snippet_chars is not None:
        params["snippet_chars"] = str(snippet_chars)
    _emit(request("GET", "/vault/semantic-search", params=params), ctx.obj["pretty"])


@search.command("hybrid")
@click.argument("query")
@click.option("--limit", type=int, help="Result cap (1..100, default 10).")
@click.option("--snippet-chars", type=int, help="Snippet length per hit (0..1000, default 300).")
@click.option("--k", type=int, help="RRF k constant (1..1000, default 60).")
@click.pass_context
def hybrid_search(
    ctx: click.Context,
    query: str,
    limit: int | None,
    snippet_chars: int | None,
    k: int | None,
) -> None:
    """Hybrid (text + semantic) search with reciprocal rank fusion."""
    params: dict[str, str] = {"q": query}
    if limit is not None:
        params["limit"] = str(limit)
    if snippet_chars is not None:
        params["snippet_chars"] = str(snippet_chars)
    if k is not None:
        params["k"] = str(k)
    _emit(request("GET", "/vault/hybrid-search", params=params), ctx.obj["pretty"])
```

- [ ] **Step 3: Run full test suite**

```bash
cd blackglass-client && uv run pytest tests/ -v
```

Expected: all tests pass (~63 total).

- [ ] **Step 4: Commit**

```bash
git add blackglass-client/src/blackglass_client/cli/search_cmds.py \
        blackglass-client/tests/test_search.py
git commit -m "feat(client): add search hybrid + --snippet-chars on all search verbs"
```

---

## Task 11: Smoke-test against live server (HITL)

**Files:** none (manual verification)

This task verifies the spec's acceptance criterion #6: `blackglass --pretty notes get foo.md` against a real server returns indented JSON.

- [ ] **Step 1: Confirm live server reachable**

Run:

```bash
BLACKGLASS_URL=http://172.16.0.3:8083 \
BLACKGLASS_API_KEY="$BLACKGLASS_API_KEY" \
uv run blackglass obs status
```

Expected: one-line JSON with `name`, `version`, `indexed_count`, etc. Exit code 0.

If unreachable: the live server may not have the latest spec endpoints. Report to user. Do not attempt to fix server-side.

- [ ] **Step 2: Verify `--pretty` against live server**

```bash
BLACKGLASS_URL=http://172.16.0.3:8083 \
BLACKGLASS_API_KEY="$BLACKGLASS_API_KEY" \
uv run blackglass --pretty vault tags
```

Expected: indented JSON output (multi-line, two-space indent).

- [ ] **Step 3: Verify error envelope against live server**

```bash
BLACKGLASS_URL=http://172.16.0.3:8083 \
BLACKGLASS_API_KEY="$BLACKGLASS_API_KEY" \
uv run blackglass notes get does-not-exist.md ; echo "exit=$?"
```

Expected: stderr contains a single JSON object with `"error": "http_error"`, `"status": 404`. Exit code `4`.

- [ ] **Step 4: No commit**

This task is verification only. No file changes.

---

## Done

After Task 11 passes, every row in the spec's command map has a working CLI verb with a passing test. The CLI is at 100% endpoint fidelity with the server.
