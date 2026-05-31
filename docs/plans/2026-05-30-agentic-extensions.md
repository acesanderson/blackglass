# Blackglass Agentic Extensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the nine endpoint additions in `docs/specs/2026-05-30-agentic-extensions.md` so blackglass agents can read in batch, edit by anchored replace, list changes, filter files by tag/frontmatter/glob, hit daily-note shortcuts, cheaply fetch metadata, atomically move notes, and search with hybrid text+semantic ranking.

**Architecture:** Each feature is a new route handler (or extension of an existing one) in `blackglass-server/src/blackglass_server/routes/`. Pure helpers go in `vault.py`, `text_utils.py`, or a new `git_utils.py`. Tests use FastAPI's `TestClient` against a `tmp_path` fixture vault. DB-touching routes are tested with monkeypatched DB functions (no real Postgres needed in unit tests).

**Tech Stack:** FastAPI, pytest, httpx TestClient, pathlib (glob), subprocess (git log), zoneinfo (Python 3.9+ stdlib).

---

## Spec reference

This plan implements `docs/specs/2026-05-30-agentic-extensions.md` v3 (anchored-replace pivot). Spec sections are referenced as "Spec §N" below. Decisions resolved in spec v3 are NOT re-litigated in the plan.

## File map

**New files:**
- `blackglass-server/src/blackglass_server/git_utils.py` — git log shell-out + parser for `/vault/changes`.
- `blackglass-server/src/blackglass_server/routes/observability_routes.py` — already exists from prior session.
- `blackglass-server/tests/conftest.py` — extend with vault fixture + TestClient fixture.
- `blackglass-server/tests/test_snippets.py`
- `blackglass-server/tests/test_meta.py`
- `blackglass-server/tests/test_batch.py`
- `blackglass-server/tests/test_daily.py`
- `blackglass-server/tests/test_filter.py`
- `blackglass-server/tests/test_changes.py`
- `blackglass-server/tests/test_replace.py`
- `blackglass-server/tests/test_hybrid.py`
- `blackglass-server/tests/test_move.py`
- `blackglass-server/tests/test_git_utils.py`

**Modified files:**
- `blackglass-server/src/blackglass_server/config.py` — add `tz: str = "UTC"` (BLACKGLASS_TZ env).
- `blackglass-server/src/blackglass_server/vault.py` — add `note_meta`, `list_files_filtered`, `move_note`, `rewrite_wikilinks`, `daily_note_path`, `read_batch`.
- `blackglass-server/src/blackglass_server/text_utils.py` — add `snippet_from_body`.
- `blackglass-server/src/blackglass_server/db.py` — add `update_embedding_path`.
- `blackglass-server/src/blackglass_server/routes/search.py` — add snippets + new hybrid route.
- `blackglass-server/src/blackglass_server/routes/notes.py` — add `replace` op + batch route.
- `blackglass-server/src/blackglass_server/routes/vault_routes.py` — add filtering on `/vault/files`, daily-note routes, meta route, changes route, move route.

## Conventions for every task

- TDD: write the failing test first, see it fail, implement minimum, see it pass, commit.
- Tests run from `blackglass-server/`:
  ```
  cd blackglass-server && uv run pytest tests/<file>.py -v
  ```
- Commits use conventional-commits with `feat(server):` or `test(server):` scope.
- `from __future__ import annotations` at the top of every new module.
- Imports on separate lines.
- No emojis, no em-dashes, no `List`/`Dict` (use `list`/`dict`), no `Optional` (use `X | None`).
- Use `Awaitable` etc. from `collections.abc`, not `typing`.

---

## Task 0: Shared test fixtures and config

**Files:**
- Modify: `blackglass-server/src/blackglass_server/config.py`
- Modify: `blackglass-server/tests/conftest.py`

- [ ] **Step 0.1: Add `tz` setting**

Edit `blackglass-server/src/blackglass_server/config.py` so the Settings class has a `tz` field:

```python
from __future__ import annotations
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    vault_path: Path
    api_key: str
    port: int = 8083
    backwater_url: str = "http://localhost:8080"
    tz: str = "UTC"

    model_config = {"env_prefix": "BLACKGLASS_"}


settings = Settings()
```

- [ ] **Step 0.2: Build a shared test fixture in conftest**

Replace `blackglass-server/tests/conftest.py` (currently a single import line) with reusable fixtures:

```python
from __future__ import annotations
import os
import subprocess
import textwrap
import pytest
from pathlib import Path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Vault with a known mix of notes, frontmatter, tags, subdirs, skip dirs."""
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".trash").mkdir()
    (tmp_path / "Work Docs" / "Sub").mkdir(parents=True)
    (tmp_path / "Daily").mkdir()

    (tmp_path / "alpha.md").write_text("AAA BBB CCC " * 20)
    (tmp_path / "beta.md").write_text(textwrap.dedent("""\
        ---
        status: in-progress
        tags: [foo]
        ---
        Beta body referencing [[alpha]].
    """))
    (tmp_path / "gamma.md").write_text(textwrap.dedent("""\
        ---
        status: done
        tags: [foo, bar]
        priority: 3
        ---
        Gamma body.
    """))
    (tmp_path / "delta.md").write_text(textwrap.dedent("""\
        ---
        archived: true
        ---
        Delta body with [[alpha|the first one]] alias link.
    """))
    (tmp_path / "Work Docs" / "foo.md").write_text("Work doc foo.")
    (tmp_path / "Work Docs" / "Sub" / "bar.md").write_text("Nested work doc bar.")
    (tmp_path / "Daily" / "2026-05-29.md").write_text("Yesterday.")
    (tmp_path / "2026-05-30.md").write_text("Daily note at root.")
    (tmp_path / ".obsidian" / "config.md").write_text("internal")
    (tmp_path / ".trash" / "old.md").write_text("trashed")
    return tmp_path


@pytest.fixture
def git_vault(vault: Path) -> Path:
    """Vault initialized as a git repo with three commits."""
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    def run(*args: str) -> None:
        subprocess.run(["git", "-C", str(vault), *args], check=True, env=env,
                       capture_output=True)
    run("init", "-q", "-b", "main")
    run("add", "-A")
    run("commit", "-q", "-m", "initial")
    (vault / "epsilon.md").write_text("new note")
    run("add", "-A")
    run("commit", "-q", "-m", "add epsilon")
    (vault / "alpha.md").write_text("AAA BBB CCC modified")
    run("add", "-A")
    run("commit", "-q", "-m", "modify alpha")
    return vault


@pytest.fixture
def client(vault: Path, monkeypatch: pytest.MonkeyPatch):
    """TestClient with settings.vault_path and api_key overridden, DB calls mocked."""
    monkeypatch.setenv("BLACKGLASS_VAULT_PATH", str(vault))
    monkeypatch.setenv("BLACKGLASS_API_KEY", "test-key")
    monkeypatch.setenv("POSTGRES_PASSWORD", "ignored")

    # Re-import settings module so env vars are read fresh.
    import importlib
    from blackglass_server import config as cfg_mod
    importlib.reload(cfg_mod)

    # Patch DB hooks to no-ops; specific tests can override.
    from blackglass_server import db as db_mod
    async def _no_pool(): return None
    monkeypatch.setattr(db_mod, "init_pool", _no_pool)
    monkeypatch.setattr(db_mod, "close_pool", _no_pool)

    from blackglass_server.main import app
    from fastapi.testclient import TestClient
    return TestClient(app, headers={"X-API-Key": "test-key"})
```

- [ ] **Step 0.3: Run existing tests to confirm nothing regressed**

Run:
```
cd blackglass-server && uv run pytest tests/test_text_utils.py tests/test_vault.py -v
```
Expected: all green.

- [ ] **Step 0.4: Commit**

```
git add blackglass-server/src/blackglass_server/config.py blackglass-server/tests/conftest.py
git commit -m "test(server): shared vault+client fixtures, tz config"
```

---

## Task 1: Snippets in search and semantic-search

Implements Spec §1.

**Files:**
- Modify: `blackglass-server/src/blackglass_server/text_utils.py`
- Modify: `blackglass-server/src/blackglass_server/routes/search.py`
- Modify: `blackglass-server/src/blackglass_server/vault.py` (extend `fulltext_search` to include snippet)
- Create: `blackglass-server/tests/test_snippets.py`

- [ ] **Step 1.1: Write failing test for `snippet_from_body` helper**

Create `blackglass-server/tests/test_snippets.py`:

```python
from __future__ import annotations
import pytest
from blackglass_server.text_utils import snippet_from_body


def test_snippet_truncates_at_whitespace():
    body = "alpha beta gamma " * 50
    snip = snippet_from_body(body, 50)
    assert len(snip) <= 50
    assert not snip.endswith("alph") and not snip.endswith("alp")
    assert snip.rstrip() == snip


def test_snippet_shorter_than_limit_returns_full():
    body = "tiny"
    assert snippet_from_body(body, 50) == "tiny"


def test_snippet_zero_chars_returns_empty():
    assert snippet_from_body("anything", 0) == ""


def test_snippet_strips_leading_whitespace():
    body = "\n\n  alpha beta"
    snip = snippet_from_body(body, 50)
    assert snip.startswith("alpha")


def test_snippet_hard_truncates_when_no_word_boundary():
    body = "A" * 200
    snip = snippet_from_body(body, 50)
    assert len(snip) == 50
```

- [ ] **Step 1.2: Run, confirm fail**

```
cd blackglass-server && uv run pytest tests/test_snippets.py -v
```
Expected: ImportError on `snippet_from_body`.

- [ ] **Step 1.3: Implement `snippet_from_body`**

Append to `blackglass-server/src/blackglass_server/text_utils.py`:

```python
def snippet_from_body(body: str, snippet_chars: int) -> str:
    if snippet_chars <= 0:
        return ""
    stripped = body.lstrip()
    if len(stripped) <= snippet_chars:
        return stripped
    window = stripped[: snippet_chars + 100]
    if snippet_chars < len(window) and window[snippet_chars - 1] in " \t\n":
        return window[:snippet_chars].rstrip()
    cut = window.rfind(" ", max(0, snippet_chars - 50), snippet_chars)
    if cut == -1:
        cut2 = window.rfind("\n", max(0, snippet_chars - 50), snippet_chars)
        if cut2 == -1:
            return window[:snippet_chars]
        cut = cut2
    return window[:cut].rstrip()
```

- [ ] **Step 1.4: Run, confirm pass**

```
cd blackglass-server && uv run pytest tests/test_snippets.py -v
```
Expected: 5 passing.

- [ ] **Step 1.5: Write failing route test for `/vault/search` snippet**

Append to `blackglass-server/tests/test_snippets.py`:

```python
def test_search_returns_snippet(client):
    r = client.get("/vault/search", params={"q": "AAA", "snippet_chars": 60})
    assert r.status_code == 200
    hits = r.json()
    paths = [h["path"] for h in hits]
    assert "alpha.md" in paths
    alpha_hit = next(h for h in hits if h["path"] == "alpha.md")
    assert "snippet" in alpha_hit
    assert len(alpha_hit["snippet"]) <= 60
    assert "AAA" in alpha_hit["snippet"]


def test_search_snippet_chars_zero_omits_field(client):
    r = client.get("/vault/search", params={"q": "AAA", "snippet_chars": 0})
    assert r.status_code == 200
    for hit in r.json():
        assert "snippet" not in hit


def test_search_default_snippet_chars_is_300(client):
    r = client.get("/vault/search", params={"q": "AAA"})
    hits = r.json()
    alpha_hit = next(h for h in hits if h["path"] == "alpha.md")
    assert "snippet" in alpha_hit
    assert len(alpha_hit["snippet"]) <= 300


def test_search_empty_q_returns_400(client):
    r = client.get("/vault/search", params={"q": ""})
    assert r.status_code == 400
```

- [ ] **Step 1.6: Read current search.py to find shape to patch**

```
cat blackglass-server/src/blackglass_server/routes/search.py
```

- [ ] **Step 1.7: Add snippet to `/vault/search` and define the helper that builds it from a path**

Replace `blackglass-server/src/blackglass_server/routes/search.py` with:

```python
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from ..auth import require_api_key
from ..config import settings
from ..vault import fulltext_search
from ..text_utils import snippet_from_body, split_frontmatter
from ..db import semantic_search
from ..embeddings import embed_text

router = APIRouter(prefix="/vault", dependencies=[Depends(require_api_key)])

_MAX_SNIPPET = 1000


def _snippet_for_path(path: str, snippet_chars: int) -> str:
    if snippet_chars <= 0:
        return ""
    try:
        text = (settings.vault_path / path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    _, body = split_frontmatter(text)
    return snippet_from_body(body, snippet_chars)


def _attach_snippet(hits: list[dict], snippet_chars: int) -> list[dict]:
    if snippet_chars <= 0:
        return hits
    for h in hits:
        h["snippet"] = _snippet_for_path(h["path"], snippet_chars)
    return hits


@router.get("/search")
def search(
    q: str = Query(...),
    snippet_chars: int = Query(default=300, ge=0, le=_MAX_SNIPPET),
) -> list[dict]:
    if not q:
        raise HTTPException(status_code=400, detail="q is required")
    hits = fulltext_search(settings.vault_path, q)
    return _attach_snippet(hits, snippet_chars)


@router.get("/semantic-search")
async def semantic(
    q: str = Query(...),
    limit: int = Query(default=10, ge=1, le=100),
    snippet_chars: int = Query(default=300, ge=0, le=_MAX_SNIPPET),
) -> list[dict]:
    if not q:
        raise HTTPException(status_code=400, detail="q is required")
    emb = await embed_text(q)
    hits = await semantic_search(emb, limit=limit)
    return _attach_snippet(hits, snippet_chars)
```

- [ ] **Step 1.8: Run search tests**

```
cd blackglass-server && uv run pytest tests/test_snippets.py -v
```
Expected: 9 passing.

- [ ] **Step 1.9: Write a failing test for semantic-search snippet via mocked DB**

Append to `blackglass-server/tests/test_snippets.py`:

```python
def test_semantic_search_attaches_snippet(client, monkeypatch):
    async def fake_embed_text(text):
        return [0.0] * 768
    async def fake_semantic_search(emb, limit=10):
        return [{"path": "alpha.md", "score": 0.9}]
    from blackglass_server.routes import search as sroute
    monkeypatch.setattr(sroute, "embed_text", fake_embed_text)
    monkeypatch.setattr(sroute, "semantic_search", fake_semantic_search)
    r = client.get("/vault/semantic-search", params={"q": "x", "snippet_chars": 80})
    assert r.status_code == 200
    hit = r.json()[0]
    assert hit["path"] == "alpha.md"
    assert "snippet" in hit
    assert "AAA" in hit["snippet"]


def test_semantic_search_missing_file_snippet_empty(client, monkeypatch):
    async def fake_embed_text(text):
        return [0.0] * 768
    async def fake_semantic_search(emb, limit=10):
        return [{"path": "ghost.md", "score": 0.5}]
    from blackglass_server.routes import search as sroute
    monkeypatch.setattr(sroute, "embed_text", fake_embed_text)
    monkeypatch.setattr(sroute, "semantic_search", fake_semantic_search)
    r = client.get("/vault/semantic-search", params={"q": "x"})
    hit = r.json()[0]
    assert hit["snippet"] == ""
```

- [ ] **Step 1.10: Run, expect pass**

```
cd blackglass-server && uv run pytest tests/test_snippets.py -v
```
Expected: 11 passing.

- [ ] **Step 1.11: Commit**

```
git add blackglass-server/src/blackglass_server/text_utils.py \
        blackglass-server/src/blackglass_server/routes/search.py \
        blackglass-server/tests/test_snippets.py
git commit -m "feat(server): snippets on /vault/search and semantic-search"
```

---

## Task 2: Metadata-only fetch

Implements Spec §7.

**Files:**
- Modify: `blackglass-server/src/blackglass_server/vault.py`
- Modify: `blackglass-server/src/blackglass_server/routes/vault_routes.py`
- Create: `blackglass-server/tests/test_meta.py`

- [ ] **Step 2.1: Write failing test**

Create `blackglass-server/tests/test_meta.py`:

```python
from __future__ import annotations


def test_meta_existing_file(client):
    r = client.get("/vault/notes/beta.md/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["exists"] is True
    assert body["path"] == "beta.md"
    assert body["size"] > 0
    assert body["mtime"] is not None
    assert body["frontmatter"] == {"status": "in-progress", "tags": ["foo"]}
    assert body["tags"] == ["foo"]
    assert body["wikilinks_count"] == 1


def test_meta_missing_file_returns_200_with_exists_false(client):
    r = client.get("/vault/notes/ghost.md/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["exists"] is False
    assert body["size"] == 0
    assert body["mtime"] is None
    assert body["frontmatter"] == {}
    assert body["tags"] == []
    assert body["wikilinks_count"] == 0


def test_meta_path_escape_400(client):
    r = client.get("/vault/notes/..%2Fescape.md/meta")
    assert r.status_code == 400


def test_meta_directory_400(client):
    r = client.get("/vault/notes/Work Docs/meta")
    assert r.status_code == 400


def test_meta_wikilinks_count_includes_duplicates(client, vault):
    (vault / "linky.md").write_text("[[a]] [[a]] [[b]] [[a|alias]]")
    r = client.get("/vault/notes/linky.md/meta")
    assert r.json()["wikilinks_count"] == 4
```

- [ ] **Step 2.2: Run, confirm fail**

```
cd blackglass-server && uv run pytest tests/test_meta.py -v
```
Expected: 404 / route not found.

- [ ] **Step 2.3: Add `note_meta` helper to vault.py**

Append to `blackglass-server/src/blackglass_server/vault.py`:

```python
def note_meta(vault_path: Path, rel_path: str) -> dict:
    p = _resolve(vault_path, rel_path)
    if p.exists() and p.is_dir():
        raise IsADirectoryError(rel_path)
    if not p.exists():
        return {
            "path": rel_path,
            "exists": False,
            "size": 0,
            "mtime": None,
            "frontmatter": {},
            "tags": [],
            "wikilinks_count": 0,
        }
    stat = p.stat()
    text = p.read_text(encoding="utf-8", errors="ignore")
    fm, body = split_frontmatter(text)
    return {
        "path": rel_path,
        "exists": True,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "frontmatter": fm,
        "tags": extract_tags(fm),
        "wikilinks_count": body.count("[["),
    }
```

- [ ] **Step 2.4: Add the route to vault_routes.py**

Append to `blackglass-server/src/blackglass_server/routes/vault_routes.py`:

```python
from fastapi import HTTPException


@router.get("/notes/{path:path}/meta")
def get_meta(path: str) -> dict:
    from ..vault import note_meta
    try:
        return note_meta(settings.vault_path, path)
    except ValueError:
        raise HTTPException(status_code=400, detail="path escapes vault")
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail="path is a directory")
```

(`settings`, `router` are already in scope from existing imports.)

- [ ] **Step 2.5: Run, confirm pass**

```
cd blackglass-server && uv run pytest tests/test_meta.py -v
```
Expected: 5 passing.

- [ ] **Step 2.6: Commit**

```
git add blackglass-server/src/blackglass_server/vault.py \
        blackglass-server/src/blackglass_server/routes/vault_routes.py \
        blackglass-server/tests/test_meta.py
git commit -m "feat(server): GET /vault/notes/{path}/meta"
```

---

## Task 3: Batch note read

Implements Spec §2.

**Files:**
- Modify: `blackglass-server/src/blackglass_server/routes/notes.py`
- Modify: `blackglass-server/src/blackglass_server/vault.py`
- Create: `blackglass-server/tests/test_batch.py`

- [ ] **Step 3.1: Write failing test**

Create `blackglass-server/tests/test_batch.py`:

```python
from __future__ import annotations


def test_batch_mixed_paths(client):
    r = client.post("/vault/notes/batch", json={"paths": ["alpha.md", "ghost.md", "../escape.md"]})
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == {"ok": 1, "not_found": 1, "error": 1}
    statuses = [x["status"] for x in body["results"]]
    assert statuses == ["ok", "not_found", "error"]
    assert body["results"][2]["error"] == "path escapes vault"
    assert body["results"][0]["note"]["path"] == "alpha.md"


def test_batch_preserves_order_with_duplicates(client):
    r = client.post("/vault/notes/batch", json={"paths": ["alpha.md", "alpha.md", "beta.md"]})
    body = r.json()
    paths = [x["path"] for x in body["results"]]
    assert paths == ["alpha.md", "alpha.md", "beta.md"]


def test_batch_empty_list_400(client):
    r = client.post("/vault/notes/batch", json={"paths": []})
    assert r.status_code == 400


def test_batch_too_many_400(client):
    r = client.post("/vault/notes/batch", json={"paths": ["alpha.md"] * 51})
    assert r.status_code == 400
```

- [ ] **Step 3.2: Run, confirm fail**

```
cd blackglass-server && uv run pytest tests/test_batch.py -v
```
Expected: 404 / route not found.

- [ ] **Step 3.3: Add the route**

Append to `blackglass-server/src/blackglass_server/routes/notes.py`:

```python
from pydantic import BaseModel


class BatchReadIn(BaseModel):
    paths: list[str]


@router.post("/batch", status_code=status.HTTP_200_OK)
def batch_read(payload: BatchReadIn) -> dict:
    from ..vault import read_note
    paths = payload.paths
    if not paths:
        raise HTTPException(status_code=400, detail="paths must be non-empty")
    if len(paths) > 50:
        raise HTTPException(status_code=400, detail="max 50 paths per batch")
    results = []
    summary = {"ok": 0, "not_found": 0, "error": 0}
    for p in paths:
        try:
            note = read_note(settings.vault_path, p)
            results.append({"path": p, "status": "ok", "note": note})
            summary["ok"] += 1
        except FileNotFoundError:
            results.append({"path": p, "status": "not_found", "error": p})
            summary["not_found"] += 1
        except ValueError:
            results.append({"path": p, "status": "error", "error": "path escapes vault"})
            summary["error"] += 1
        except OSError as exc:
            results.append({"path": p, "status": "error", "error": type(exc).__name__})
            summary["error"] += 1
    return {"results": results, "summary": summary}
```

Note: the prefix in `routes/notes.py` is `/vault/notes`, so this lands at `POST /vault/notes/batch` as the spec requires. Confirm by reading the existing `router = APIRouter(prefix=...)` line.

- [ ] **Step 3.4: Run, confirm pass**

```
cd blackglass-server && uv run pytest tests/test_batch.py -v
```
Expected: 4 passing.

- [ ] **Step 3.5: Commit**

```
git add blackglass-server/src/blackglass_server/routes/notes.py \
        blackglass-server/tests/test_batch.py
git commit -m "feat(server): POST /vault/notes/batch"
```

---

## Task 4: Daily-note shortcuts

Implements Spec §6.

**Files:**
- Modify: `blackglass-server/src/blackglass_server/vault.py`
- Modify: `blackglass-server/src/blackglass_server/routes/vault_routes.py`
- Create: `blackglass-server/tests/test_daily.py`

- [ ] **Step 4.1: Write failing test**

Create `blackglass-server/tests/test_daily.py`:

```python
from __future__ import annotations
import datetime
import zoneinfo


def _today_in_tz(tz: str) -> str:
    return datetime.datetime.now(zoneinfo.ZoneInfo(tz)).strftime("%Y-%m-%d")


def test_today_auto_creates_on_first_get(client, vault):
    today = _today_in_tz("UTC")
    target = vault / f"{today}.md"
    if target.exists():
        target.unlink()
    r = client.get("/vault/periodic/today")
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True
    assert body["path"] == f"{today}.md"
    assert target.exists()


def test_today_second_get_not_created(client, vault):
    today = _today_in_tz("UTC")
    (vault / f"{today}.md").write_text("exists")
    r = client.get("/vault/periodic/today")
    assert r.json()["created"] is False


def test_by_date_invalid_format_400(client):
    r = client.get("/vault/periodic/by-date/2026-13-01")
    assert r.status_code == 400


def test_by_date_out_of_range_400(client):
    r = client.get("/vault/periodic/by-date/1969-12-31")
    assert r.status_code == 400
    r2 = client.get("/vault/periodic/by-date/2100-01-01")
    assert r2.status_code == 400


def test_append_creates_then_appends(client, vault):
    today = _today_in_tz("UTC")
    target = vault / f"{today}.md"
    if target.exists():
        target.unlink()
    r1 = client.post("/vault/periodic/today/append", json={"content": "one\n"})
    assert r1.status_code == 200
    r2 = client.post("/vault/periodic/today/append", json={"content": "two\n"})
    assert r2.status_code == 200
    assert target.read_text() == "one\ntwo\n"
```

- [ ] **Step 4.2: Run, confirm fail**

```
cd blackglass-server && uv run pytest tests/test_daily.py -v
```
Expected: 404 / route not found.

- [ ] **Step 4.3: Add daily-note helpers to vault.py**

Append to `blackglass-server/src/blackglass_server/vault.py`:

```python
import datetime
import zoneinfo


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
        p.touch()
    return p, created
```

- [ ] **Step 4.4: Add the daily routes to vault_routes.py**

Append to `blackglass-server/src/blackglass_server/routes/vault_routes.py`:

```python
from fastapi import Body


@router.get("/periodic/today")
def periodic_today() -> dict:
    from ..vault import today_in_tz, ensure_daily_note, read_note
    date_str = today_in_tz(settings.tz)
    _, created = ensure_daily_note(settings.vault_path, date_str)
    note = read_note(settings.vault_path, f"{date_str}.md")
    note["created"] = created
    return note


@router.get("/periodic/yesterday")
def periodic_yesterday() -> dict:
    from ..vault import yesterday_in_tz, ensure_daily_note, read_note
    date_str = yesterday_in_tz(settings.tz)
    _, created = ensure_daily_note(settings.vault_path, date_str)
    note = read_note(settings.vault_path, f"{date_str}.md")
    note["created"] = created
    return note


@router.get("/periodic/by-date/{date_str}")
def periodic_by_date(date_str: str) -> dict:
    from ..vault import ensure_daily_note, read_note
    try:
        _, created = ensure_daily_note(settings.vault_path, date_str)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    note = read_note(settings.vault_path, f"{date_str}.md")
    note["created"] = created
    return note


@router.post("/periodic/today/append")
def periodic_today_append(content: str = Body(..., embed=True)) -> dict:
    from ..vault import today_in_tz, ensure_daily_note, read_note
    date_str = today_in_tz(settings.tz)
    p, _ = ensure_daily_note(settings.vault_path, date_str)
    with p.open("a", encoding="utf-8") as f:
        f.write(content)
    return read_note(settings.vault_path, f"{date_str}.md")
```

- [ ] **Step 4.5: Run, confirm pass**

```
cd blackglass-server && uv run pytest tests/test_daily.py -v
```
Expected: 5 passing.

- [ ] **Step 4.6: Commit**

```
git add blackglass-server/src/blackglass_server/vault.py \
        blackglass-server/src/blackglass_server/routes/vault_routes.py \
        blackglass-server/tests/test_daily.py
git commit -m "feat(server): /vault/periodic daily-note shortcuts"
```

---

## Task 5: Filtering on `/vault/files`

Implements Spec §4.

**Files:**
- Modify: `blackglass-server/src/blackglass_server/vault.py`
- Modify: `blackglass-server/src/blackglass_server/routes/vault_routes.py`
- Create: `blackglass-server/tests/test_filter.py`

- [ ] **Step 5.1: Write failing test**

Create `blackglass-server/tests/test_filter.py`:

```python
from __future__ import annotations


def test_files_no_filter_returns_legacy_shape(client):
    r = client.get("/vault/files")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert all("path" in f and "size" in f for f in body)


def test_files_tag_filter(client):
    r = client.get("/vault/files", params={"tag": "foo"})
    body = r.json()
    paths = [f["path"] for f in body["files"]]
    assert set(paths) == {"beta.md", "gamma.md"}
    assert body["total"] == 2
    assert body["filtered_from"] >= 2


def test_files_tag_and_filter(client):
    r = client.get("/vault/files", params=[("tag", "foo"), ("tag", "bar")])
    body = r.json()
    paths = [f["path"] for f in body["files"]]
    assert paths == ["gamma.md"]


def test_files_fm_string(client):
    r = client.get("/vault/files", params={"fm.status": "in-progress"})
    paths = [f["path"] for f in r.json()["files"]]
    assert paths == ["beta.md"]


def test_files_fm_number(client):
    r = client.get("/vault/files", params={"fm.priority": "3"})
    paths = [f["path"] for f in r.json()["files"]]
    assert paths == ["gamma.md"]


def test_files_fm_bool(client):
    r = client.get("/vault/files", params={"fm.archived": "true"})
    paths = [f["path"] for f in r.json()["files"]]
    assert paths == ["delta.md"]


def test_files_path_glob_direct_children(client):
    r = client.get("/vault/files", params={"path_glob": "Work Docs/*.md"})
    paths = [f["path"] for f in r.json()["files"]]
    assert paths == ["Work Docs/foo.md"]


def test_files_path_glob_recursive(client):
    r = client.get("/vault/files", params={"path_glob": "Work Docs/**/*.md"})
    paths = sorted(f["path"] for f in r.json()["files"])
    assert paths == ["Work Docs/Sub/bar.md", "Work Docs/foo.md"]


def test_files_dup_fm_400(client):
    r = client.get("/vault/files", params=[("fm.status", "x"), ("fm.status", "y")])
    assert r.status_code == 400


def test_files_nested_fm_key_400(client):
    r = client.get("/vault/files", params={"fm.a.b": "x"})
    assert r.status_code == 400
```

- [ ] **Step 5.2: Run, confirm fail**

```
cd blackglass-server && uv run pytest tests/test_filter.py -v
```
Expected: fixture tests fail because the route returns the legacy list shape regardless of filters.

- [ ] **Step 5.3: Add `list_files_filtered` to vault.py**

Append to `blackglass-server/src/blackglass_server/vault.py`:

```python
from pathlib import PurePosixPath


def _fm_value_matches(fm_value, query: str) -> bool:
    if isinstance(fm_value, dict):
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
) -> tuple[list[dict], int]:
    tags = tags or []
    fm_filters = fm_filters or {}
    all_files = list_files(vault_path)
    filtered: list[dict] = []
    for f in all_files:
        rel = f["path"]
        if path_glob is not None and not PurePosixPath(rel).match(path_glob):
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
    return filtered, total_before_limit
```

- [ ] **Step 5.4: Update `/vault/files` to apply filters**

Edit `blackglass-server/src/blackglass_server/routes/vault_routes.py`. Replace the existing `/files` handler with a filter-aware version. Find:

```python
@router.get("/files")
def files():
    return list_files(settings.vault_path)
```

Replace with:

```python
from fastapi import Request


@router.get("/files")
def files(request: Request, limit: int | None = None):
    from ..vault import list_files, list_files_filtered
    raw = request.query_params
    tags = raw.getlist("tag") if hasattr(raw, "getlist") else raw.multi_items()
    if hasattr(raw, "getlist"):
        tag_list = raw.getlist("tag")
    else:
        tag_list = [v for k, v in raw.multi_items() if k == "tag"]
    fm_filters: dict[str, str] = {}
    seen_fm: set[str] = set()
    for key, val in raw.multi_items():
        if not key.startswith("fm."):
            continue
        bare = key[3:]
        if "." in bare:
            raise HTTPException(status_code=400, detail="nested keys not supported")
        if bare in seen_fm:
            raise HTTPException(status_code=400, detail=f"duplicate filter key: fm.{bare}")
        seen_fm.add(bare)
        fm_filters[bare] = val
    path_glob = raw.get("path_glob")
    if path_glob is not None and ".." in PurePosixPath(path_glob).parts:
        raise HTTPException(status_code=400, detail="path_glob may not contain '..'")
    has_filter = bool(tag_list or fm_filters or path_glob or limit)
    if not has_filter:
        return list_files(settings.vault_path)
    filtered, total = list_files_filtered(
        settings.vault_path,
        tags=tag_list,
        fm_filters=fm_filters,
        path_glob=path_glob,
        limit=limit,
    )
    all_count = len(list_files(settings.vault_path))
    return {"files": filtered, "total": total, "filtered_from": all_count}
```

Add at the top of the file:

```python
from pathlib import PurePosixPath
```

- [ ] **Step 5.5: Run, confirm pass**

```
cd blackglass-server && uv run pytest tests/test_filter.py -v
```
Expected: 10 passing.

- [ ] **Step 5.6: Commit**

```
git add blackglass-server/src/blackglass_server/vault.py \
        blackglass-server/src/blackglass_server/routes/vault_routes.py \
        blackglass-server/tests/test_filter.py
git commit -m "feat(server): tag/frontmatter/glob filters on /vault/files"
```

---

## Task 6: Recent / changes endpoint

Implements Spec §3.

**Files:**
- Create: `blackglass-server/src/blackglass_server/git_utils.py`
- Modify: `blackglass-server/src/blackglass_server/routes/vault_routes.py`
- Create: `blackglass-server/tests/test_git_utils.py`
- Create: `blackglass-server/tests/test_changes.py`

- [ ] **Step 6.1: Write failing test for the git parser**

Create `blackglass-server/tests/test_git_utils.py`:

```python
from __future__ import annotations
from blackglass_server.git_utils import parse_name_status, parse_numstat


def test_parse_name_status_added_modified():
    raw = "abc123\x1f1780115422\x1fmodify alpha\x1eM\talpha.md\x1edef456\x1f1780115000\x1fadd epsilon\x1eA\tepsilon.md"
    out = parse_name_status(raw)
    assert len(out) == 2
    assert out[0]["commit"] == "abc123"
    assert out[0]["timestamp"] == 1780115422.0
    assert out[0]["subject"] == "modify alpha"
    assert out[0]["changes"] == [{"change": "modified", "path": "alpha.md", "from_path": None}]


def test_parse_name_status_renamed():
    raw = "c1\x1f100\x1fr1\x1eR100\told.md\tnew.md"
    out = parse_name_status(raw)
    assert out[0]["changes"][0] == {"change": "renamed", "path": "new.md", "from_path": "old.md"}


def test_parse_numstat_basic():
    raw = "c1\x1f100\x1fr1\x1e3\t1\talpha.md\n0\t0\tbinary.png"
    out = parse_numstat(raw)
    assert out["c1"] == {"alpha.md": {"added": 3, "removed": 1}}
```

- [ ] **Step 6.2: Run, confirm fail**

```
cd blackglass-server && uv run pytest tests/test_git_utils.py -v
```
Expected: ImportError.

- [ ] **Step 6.3: Implement `git_utils.py`**

Create `blackglass-server/src/blackglass_server/git_utils.py`:

```python
from __future__ import annotations
import subprocess
from pathlib import Path

_CHANGE_LETTER = {
    "A": "added",
    "M": "modified",
    "D": "deleted",
    "R": "renamed",
    "C": "copied",
    "T": "type_changed",
}


def parse_name_status(raw: str) -> list[dict]:
    commits: list[dict] = []
    if not raw:
        return commits
    for chunk in raw.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        header, _, files_blob = chunk.partition("\n")
        parts = header.split("\x1f")
        if len(parts) != 3:
            continue
        commit, ts_str, subject = parts
        try:
            ts = float(ts_str)
        except ValueError:
            continue
        changes = []
        for line in files_blob.splitlines():
            if not line:
                continue
            cols = line.split("\t")
            letter = cols[0][:1]
            change = _CHANGE_LETTER.get(letter)
            if change is None:
                continue
            if change in ("renamed", "copied") and len(cols) >= 3:
                from_path, path = cols[1], cols[2]
            else:
                from_path = None
                path = cols[1] if len(cols) >= 2 else ""
            try:
                path.encode("utf-8")
            except UnicodeError:
                continue
            changes.append({"change": change, "path": path, "from_path": from_path})
        commits.append({"commit": commit, "timestamp": ts, "subject": subject, "changes": changes})
    return commits


def parse_numstat(raw: str) -> dict[str, dict[str, dict[str, int]]]:
    out: dict[str, dict[str, dict[str, int]]] = {}
    for chunk in raw.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        header, _, files_blob = chunk.partition("\n")
        parts = header.split("\x1f")
        if not parts:
            continue
        commit = parts[0]
        per_file: dict[str, dict[str, int]] = {}
        for line in files_blob.splitlines():
            if not line:
                continue
            cols = line.split("\t")
            if len(cols) < 3:
                continue
            added_s, removed_s, path = cols[0], cols[1], cols[2]
            try:
                added = int(added_s)
                removed = int(removed_s)
            except ValueError:
                continue
            per_file[path] = {"added": added, "removed": removed}
        out[commit] = per_file
    return out


def git_changes(
    vault_path: Path,
    since_epoch: float,
    include_diff_stats: bool = False,
    timeout: float = 10.0,
) -> list[dict]:
    pretty = "--pretty=format:%H\x1f%ct\x1f%s\x1e"
    proc = subprocess.run(
        ["git", "-C", str(vault_path), "log", f"--since={int(since_epoch)}",
         "--name-status", pretty],
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git log failed")
    commits = parse_name_status(proc.stdout)
    if include_diff_stats:
        proc2 = subprocess.run(
            ["git", "-C", str(vault_path), "log", f"--since={int(since_epoch)}",
             "--numstat", pretty],
            capture_output=True, text=True, timeout=timeout,
        )
        if proc2.returncode == 0:
            stats = parse_numstat(proc2.stdout)
            for c in commits:
                per_file = stats.get(c["commit"], {})
                for ch in c["changes"]:
                    ch["diff_stats"] = per_file.get(ch["path"])
    return commits
```

- [ ] **Step 6.4: Run parser tests**

```
cd blackglass-server && uv run pytest tests/test_git_utils.py -v
```
Expected: 3 passing.

- [ ] **Step 6.5: Write failing route test**

Create `blackglass-server/tests/test_changes.py`:

```python
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def git_client(git_vault, monkeypatch):
    monkeypatch.setenv("BLACKGLASS_VAULT_PATH", str(git_vault))
    monkeypatch.setenv("BLACKGLASS_API_KEY", "test-key")
    monkeypatch.setenv("POSTGRES_PASSWORD", "ignored")
    import importlib
    from blackglass_server import config as cfg_mod
    importlib.reload(cfg_mod)
    from blackglass_server import db as db_mod
    async def _noop(): return None
    monkeypatch.setattr(db_mod, "init_pool", _noop)
    monkeypatch.setattr(db_mod, "close_pool", _noop)
    from blackglass_server.main import app
    return TestClient(app, headers={"X-API-Key": "test-key"})


def test_changes_recent(git_client):
    r = git_client.get("/vault/changes", params={"days": 30})
    assert r.status_code == 200
    body = r.json()
    paths = [c["path"] for c in body["changes"]]
    assert "alpha.md" in paths
    assert "epsilon.md" in paths
    assert any(c["change"] == "added" for c in body["changes"])


def test_changes_limit_one(git_client):
    r = git_client.get("/vault/changes", params={"days": 30, "limit": 1})
    body = r.json()
    assert len(body["changes"]) == 1
    assert body["truncated"] is True


def test_changes_days_zero_400(git_client):
    r = git_client.get("/vault/changes", params={"days": 0})
    assert r.status_code == 400


def test_changes_since_unparseable_400(git_client):
    r = git_client.get("/vault/changes", params={"since": "tomorrow"})
    assert r.status_code == 400


def test_changes_both_params_400(git_client):
    r = git_client.get("/vault/changes", params={"since": "1700000000", "days": 7})
    assert r.status_code == 400


def test_changes_not_a_repo_400(client):
    r = client.get("/vault/changes", params={"days": 7})
    assert r.status_code == 400
```

- [ ] **Step 6.6: Run, confirm fail**

```
cd blackglass-server && uv run pytest tests/test_changes.py -v
```
Expected: 404 / route missing.

- [ ] **Step 6.7: Add `/vault/changes` route**

Append to `blackglass-server/src/blackglass_server/routes/vault_routes.py`:

```python
import datetime
import time as _time
from fastapi import Query


_SKIP_DIRS = ("/.obsidian/", "/.trash/")


def _parse_since(since: str) -> float:
    try:
        return float(since)
    except ValueError:
        pass
    s = since.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(s).timestamp()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unparseable since: {since}") from exc


@router.get("/changes")
def vault_changes(
    since: str | None = None,
    days: int | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    include_diff_stats: bool = False,
) -> dict:
    if since is not None and days is not None:
        raise HTTPException(status_code=400, detail="pass either since or days, not both")
    if days is not None and (days < 1 or days > 365):
        raise HTTPException(status_code=400, detail="days must be in [1, 365]")
    if since is None and days is None:
        days = 7
    if days is not None:
        since_epoch = _time.time() - days * 86400
    else:
        since_epoch = _parse_since(since)

    if not (settings.vault_path / ".git").exists():
        raise HTTPException(status_code=400, detail="vault is not a git repository")

    from ..git_utils import git_changes
    try:
        commits = git_changes(settings.vault_path, since_epoch, include_diff_stats)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    flat: list[dict] = []
    for c in commits:
        for ch in c["changes"]:
            normalized = "/" + ch["path"]
            if any(s in normalized for s in _SKIP_DIRS):
                continue
            flat.append({
                "path": ch["path"],
                "change": ch["change"],
                "commit": c["commit"][:7],
                "timestamp": c["timestamp"],
                "subject": c["subject"],
                "from_path": ch["from_path"],
                "diff_stats": ch.get("diff_stats"),
            })
    flat.sort(key=lambda x: x["timestamp"], reverse=True)
    truncated = len(flat) > limit
    return {
        "since": since_epoch,
        "limit": limit,
        "changes": flat[:limit],
        "truncated": truncated,
    }
```

- [ ] **Step 6.8: Run, confirm pass**

```
cd blackglass-server && uv run pytest tests/test_changes.py -v
```
Expected: 6 passing.

- [ ] **Step 6.9: Commit**

```
git add blackglass-server/src/blackglass_server/git_utils.py \
        blackglass-server/src/blackglass_server/routes/vault_routes.py \
        blackglass-server/tests/test_git_utils.py \
        blackglass-server/tests/test_changes.py
git commit -m "feat(server): GET /vault/changes backed by git log"
```

---

## Task 7: Anchored `replace` PATCH op

Implements Spec §5.

**Files:**
- Modify: `blackglass-server/src/blackglass_server/routes/notes.py`
- Create: `blackglass-server/tests/test_replace.py`

- [ ] **Step 7.1: Read current PATCH handler**

```
sed -n '/PATCH/,/^@/p' blackglass-server/src/blackglass_server/routes/notes.py
```

Note the current shape (`op=append` and `op=set_frontmatter`). The new op will branch alongside them.

- [ ] **Step 7.2: Write failing tests**

Create `blackglass-server/tests/test_replace.py`:

```python
from __future__ import annotations
from pathlib import Path


def test_replace_unique_ok(client, vault):
    (vault / "simple.md").write_text("alpha beta gamma")
    r = client.patch("/vault/notes/simple.md", json={
        "op": "replace", "old": "beta", "new": "DELTA"
    })
    assert r.status_code == 200
    body = r.json()
    assert body["replacements"] == 1
    assert (vault / "simple.md").read_text() == "alpha DELTA gamma"


def test_replace_not_found_404(client, vault):
    (vault / "simple.md").write_text("alpha beta gamma")
    r = client.patch("/vault/notes/simple.md", json={
        "op": "replace", "old": "zeta", "new": "X"
    })
    assert r.status_code == 404
    assert (vault / "simple.md").read_text() == "alpha beta gamma"


def test_replace_ambiguous_409(client, vault):
    (vault / "many.md").write_text("x x x")
    r = client.patch("/vault/notes/many.md", json={
        "op": "replace", "old": "x", "new": "y"
    })
    assert r.status_code == 409
    body = r.json()
    assert body["detail"]["match_count"] == 3
    assert (vault / "many.md").read_text() == "x x x"


def test_replace_all_ok(client, vault):
    (vault / "many.md").write_text("x x x")
    r = client.patch("/vault/notes/many.md", json={
        "op": "replace", "old": "x", "new": "y", "replace_all": True
    })
    assert r.status_code == 200
    assert r.json()["replacements"] == 3
    assert (vault / "many.md").read_text() == "y y y"


def test_replace_empty_old_400(client, vault):
    (vault / "x.md").write_text("a")
    r = client.patch("/vault/notes/x.md", json={
        "op": "replace", "old": "", "new": "X"
    })
    assert r.status_code == 400


def test_replace_deletes_when_new_empty(client, vault):
    (vault / "x.md").write_text("hello world")
    r = client.patch("/vault/notes/x.md", json={
        "op": "replace", "old": "world", "new": ""
    })
    assert r.status_code == 200
    assert (vault / "x.md").read_text() == "hello "


def test_replace_multiline_section(client, vault):
    (vault / "doc.md").write_text("# Top\n## Tasks\nold body\n## Next\ntail")
    r = client.patch("/vault/notes/doc.md", json={
        "op": "replace",
        "old": "## Tasks\nold body\n## Next",
        "new": "## Tasks\nnew body line 1\nnew body line 2\n## Next",
    })
    assert r.status_code == 200
    assert "new body line 1" in (vault / "doc.md").read_text()


def test_replace_crlf_does_not_match_lf(client, vault):
    (vault / "lf.md").write_text("a\nb\nc")
    r = client.patch("/vault/notes/lf.md", json={
        "op": "replace", "old": "a\r\nb", "new": "Z"
    })
    assert r.status_code == 404


def test_replace_old_too_large_413(client, vault):
    (vault / "x.md").write_text("a")
    r = client.patch("/vault/notes/x.md", json={
        "op": "replace", "old": "x" * (1024 * 1024 + 1), "new": "y"
    })
    assert r.status_code == 413
```

- [ ] **Step 7.3: Run, confirm fail**

```
cd blackglass-server && uv run pytest tests/test_replace.py -v
```
Expected: 422 / unknown op / wrong behavior on most.

- [ ] **Step 7.4: Add the `replace` branch to the PATCH handler**

Edit the existing PATCH handler in `blackglass-server/src/blackglass_server/routes/notes.py` so the op-dispatch covers `replace`. Find the existing `if op == "append"` / `elif op == "set_frontmatter"` block; add an `elif op == "replace"` branch:

```python
        elif op == "replace":
            old = body.get("old", "")
            new = body.get("new", "")
            replace_all = bool(body.get("replace_all", False))
            if not isinstance(old, str) or not isinstance(new, str):
                raise HTTPException(status_code=400, detail="old and new must be strings")
            if old == "":
                raise HTTPException(status_code=400, detail="old must be non-empty")
            if len(old) > 1024 * 1024 or len(new) > 1024 * 1024:
                raise HTTPException(status_code=413, detail="old/new exceeds 1 MiB")
            current = note["content"]
            count = current.count(old)
            if count == 0:
                raise HTTPException(status_code=404, detail="old not found in file")
            if count > 1 and not replace_all:
                raise HTTPException(status_code=409, detail={
                    "message": "old matched multiple times; set replace_all=true or widen anchor",
                    "match_count": count,
                })
            updated = current.replace(old, new) if replace_all else current.replace(old, new, 1)
            if len(updated.encode("utf-8")) > 10 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="file would exceed 10 MiB")
            write_note(settings.vault_path, path, updated)
            result = read_note(settings.vault_path, path)
            result["replacements"] = count if replace_all else 1
            return result
```

Adjust surrounding code so `note` (the pre-PATCH read), `current`, and the existing `path`/`body` variables are reused with the existing branch's names. If the current handler reads the file at the top and stores it as `note`, share that. If not, add `note = read_note(settings.vault_path, path)` at the branch top.

- [ ] **Step 7.5: Run, confirm pass**

```
cd blackglass-server && uv run pytest tests/test_replace.py -v
```
Expected: 9 passing.

- [ ] **Step 7.6: Commit**

```
git add blackglass-server/src/blackglass_server/routes/notes.py \
        blackglass-server/tests/test_replace.py
git commit -m "feat(server): anchored replace PATCH op"
```

- [ ] **Step 7.7: Add PATCH /vault/periodic/today wrapper**

The spec defines `PATCH /vault/periodic/today` (Spec §6 routes). It delegates to the same dispatch as `PATCH /vault/notes/{path}` once today's note path is resolved.

In `blackglass-server/src/blackglass_server/routes/vault_routes.py`, add:

```python
@router.patch("/periodic/today")
def periodic_today_patch(body: dict) -> dict:
    date_str = today_in_tz(settings.tz)
    ensure_daily_note(settings.vault_path, date_str)
    from .notes import patch_note  # shares op dispatch
    return patch_note(f"{date_str}.md", body)
```

(If `patch_note` is not a directly-callable handler — i.e., it's a FastAPI route function — extract the op-dispatch body into a helper `_apply_patch(path: str, body: dict) -> dict` in `routes/notes.py` and have both PATCH routes call it.)

Add to `blackglass-server/tests/test_daily.py`:

```python
def test_patch_today_replace(client, vault):
    import datetime, zoneinfo
    today = datetime.datetime.now(zoneinfo.ZoneInfo("UTC")).strftime("%Y-%m-%d")
    target = vault / f"{today}.md"
    if target.exists():
        target.unlink()
    # First create + populate via append
    client.post("/vault/periodic/today/append", json={"content": "old line\n"})
    r = client.patch("/vault/periodic/today", json={
        "op": "replace", "old": "old line", "new": "new line"
    })
    assert r.status_code == 200
    assert target.read_text() == "new line\n"
```

---

## Task 8: Hybrid text + semantic search

Implements Spec §9.

**Files:**
- Modify: `blackglass-server/src/blackglass_server/routes/search.py`
- Create: `blackglass-server/tests/test_hybrid.py`

- [ ] **Step 8.1: Write failing tests**

Create `blackglass-server/tests/test_hybrid.py`:

```python
from __future__ import annotations


def _fake_embed(text):
    async def inner(): return [0.0] * 768
    return inner


def test_hybrid_combines_text_and_semantic(client, monkeypatch):
    from blackglass_server.routes import search as sroute
    async def embed(text): return [0.0] * 768
    async def sem(emb, limit=10):
        return [
            {"path": "alpha.md", "score": 0.9},
            {"path": "beta.md", "score": 0.7},
        ]
    monkeypatch.setattr(sroute, "embed_text", embed)
    monkeypatch.setattr(sroute, "semantic_search", sem)
    r = client.get("/vault/hybrid-search", params={"q": "AAA", "limit": 5})
    assert r.status_code == 200
    hits = r.json()
    paths = [h["path"] for h in hits]
    assert "alpha.md" in paths
    alpha = next(h for h in hits if h["path"] == "alpha.md")
    assert "text" in alpha["sources"] or "semantic" in alpha["sources"]
    assert alpha["sources"] == sorted(alpha["sources"])
    assert "snippet" in alpha


def test_hybrid_sources_sorted_alpha(client, monkeypatch):
    from blackglass_server.routes import search as sroute
    async def embed(text): return [0.0] * 768
    async def sem(emb, limit=10): return [{"path": "alpha.md", "score": 0.9}]
    monkeypatch.setattr(sroute, "embed_text", embed)
    monkeypatch.setattr(sroute, "semantic_search", sem)
    r = client.get("/vault/hybrid-search", params={"q": "AAA"})
    alpha = next(h for h in r.json() if h["path"] == "alpha.md")
    assert alpha["sources"] == ["semantic", "text"]


def test_hybrid_backwater_down_returns_degraded(client, monkeypatch):
    from blackglass_server.routes import search as sroute
    import httpx
    async def embed(text):
        raise httpx.ConnectError("backwater down")
    async def sem(emb, limit=10): return []
    monkeypatch.setattr(sroute, "embed_text", embed)
    monkeypatch.setattr(sroute, "semantic_search", sem)
    r = client.get("/vault/hybrid-search", params={"q": "AAA"})
    assert r.status_code == 200
    # Response is a list; degraded surfaces via a special last entry envelope?
    # We model degraded as a top-level field. Use a wrapper for hybrid.
    assert isinstance(r.json(), dict) or any("AAA" in h.get("snippet", "") for h in r.json())


def test_hybrid_empty_q_400(client):
    r = client.get("/vault/hybrid-search", params={"q": ""})
    assert r.status_code == 400
```

Note: the test for backwater-down expects a `degraded` indicator. The spec says it is "a field" in the response. Switching the route to return an object `{results: [...], degraded: "..."}` would be cleaner than smuggling a sentinel into a list. The plan adopts the object shape — update spec wording if desired, but it remains additive.

- [ ] **Step 8.2: Run, confirm fail**

```
cd blackglass-server && uv run pytest tests/test_hybrid.py -v
```
Expected: 404 / route missing.

- [ ] **Step 8.3: Implement hybrid-search**

Append to `blackglass-server/src/blackglass_server/routes/search.py`:

```python
import asyncio
import httpx


def _rrf(rank: int, k: int) -> float:
    return 1.0 / (k + rank)


@router.get("/hybrid-search")
async def hybrid_search(
    q: str = Query(...),
    limit: int = Query(default=10, ge=1, le=100),
    snippet_chars: int = Query(default=300, ge=0, le=_MAX_SNIPPET),
    k: int = Query(default=60, ge=1, le=1000),
):
    if not q:
        raise HTTPException(status_code=400, detail="q is required")

    pull = limit * 3
    text_hits = fulltext_search(settings.vault_path, q)[:pull]

    sem_hits: list[dict] = []
    degraded: str | None = None
    try:
        emb = await embed_text(q)
        sem_hits = await semantic_search(emb, limit=pull)
    except (httpx.HTTPError, httpx.ConnectError):
        degraded = "semantic_unavailable"

    scores: dict[str, dict] = {}
    for i, h in enumerate(text_hits, start=1):
        path = h["path"]
        bucket = scores.setdefault(path, {"path": path, "score": 0.0,
                                          "sources": set(), "text_rank": None,
                                          "semantic_rank": None,
                                          "text_excerpt": h.get("excerpt")})
        bucket["score"] += _rrf(i, k)
        bucket["sources"].add("text")
        bucket["text_rank"] = i

    for i, h in enumerate(sem_hits, start=1):
        path = h["path"]
        bucket = scores.setdefault(path, {"path": path, "score": 0.0,
                                          "sources": set(), "text_rank": None,
                                          "semantic_rank": None,
                                          "text_excerpt": None})
        bucket["score"] += _rrf(i, k)
        bucket["sources"].add("semantic")
        bucket["semantic_rank"] = i

    ranked = sorted(scores.values(), key=lambda b: b["score"], reverse=True)[:limit]
    out = []
    for b in ranked:
        snippet = ""
        if snippet_chars > 0:
            if b["text_excerpt"]:
                snippet = b["text_excerpt"][:snippet_chars]
            else:
                snippet = _snippet_for_path(b["path"], snippet_chars)
        out.append({
            "path": b["path"],
            "score": b["score"],
            "snippet": snippet,
            "sources": sorted(b["sources"]),
            "text_rank": b["text_rank"],
            "semantic_rank": b["semantic_rank"],
        })
    return {"results": out, "degraded": degraded}
```

Now update the hybrid tests to match the `{results, degraded}` object shape:

Replace the third test in `tests/test_hybrid.py` with:

```python
def test_hybrid_backwater_down_returns_degraded(client, monkeypatch):
    from blackglass_server.routes import search as sroute
    import httpx
    async def embed(text):
        raise httpx.ConnectError("backwater down")
    async def sem(emb, limit=10): return []
    monkeypatch.setattr(sroute, "embed_text", embed)
    monkeypatch.setattr(sroute, "semantic_search", sem)
    r = client.get("/vault/hybrid-search", params={"q": "AAA"})
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] == "semantic_unavailable"
    assert any(h["path"] == "alpha.md" for h in body["results"])
```

Adjust the first two tests' `r.json()` calls to read `r.json()["results"]`:

```python
def test_hybrid_combines_text_and_semantic(client, monkeypatch):
    ...
    hits = r.json()["results"]
    ...

def test_hybrid_sources_sorted_alpha(client, monkeypatch):
    ...
    alpha = next(h for h in r.json()["results"] if h["path"] == "alpha.md")
    ...
```

- [ ] **Step 8.4: Run, confirm pass**

```
cd blackglass-server && uv run pytest tests/test_hybrid.py -v
```
Expected: 4 passing.

- [ ] **Step 8.5: Commit**

```
git add blackglass-server/src/blackglass_server/routes/search.py \
        blackglass-server/tests/test_hybrid.py
git commit -m "feat(server): /vault/hybrid-search with RRF merge"
```

---

## Task 9: Move + wikilink rewrite

Implements Spec §8.

**Files:**
- Modify: `blackglass-server/src/blackglass_server/vault.py`
- Modify: `blackglass-server/src/blackglass_server/db.py`
- Modify: `blackglass-server/src/blackglass_server/routes/vault_routes.py`
- Create: `blackglass-server/tests/test_move.py`

- [ ] **Step 9.1: Add `update_embedding_path` to db.py**

Append to `blackglass-server/src/blackglass_server/db.py`:

```python
async def update_embedding_path(old: str, new: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM vault_embeddings WHERE path=$1", new)
            await conn.execute("UPDATE vault_embeddings SET path=$1 WHERE path=$2", new, old)
```

- [ ] **Step 9.2: Add `rewrite_wikilinks` + `move_note` to vault.py**

Append to `blackglass-server/src/blackglass_server/vault.py`:

```python
import re


def _wikilink_patterns(old_stem: str, new_stem: str) -> list[tuple[re.Pattern, str]]:
    o = re.escape(old_stem)
    n = new_stem.replace("\\", r"\\")
    pats = [
        (re.compile(rf"(!?)\[\[{o}\]\]"), rf"\1[[{n}]]"),
        (re.compile(rf"(!?)\[\[{o}\|([^\]]+)\]\]"), rf"\1[[{n}|\2]]"),
        (re.compile(rf"(!?)\[\[{o}#([^\]\|]+)\]\]"), rf"\1[[{n}#\2]]"),
        (re.compile(rf"(!?)\[\[{o}#([^\]\|]+)\|([^\]]+)\]\]"), rf"\1[[{n}#\2|\3]]"),
    ]
    return pats


def rewrite_wikilinks(
    vault_path: Path,
    old_rel: str,
    new_rel: str,
) -> tuple[list[str], list[dict]]:
    old_stem = Path(old_rel).stem
    new_stem = Path(new_rel).stem
    patterns = _wikilink_patterns(old_stem, new_stem)
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
```

- [ ] **Step 9.3: Write failing route test**

Create `blackglass-server/tests/test_move.py`:

```python
from __future__ import annotations
import pytest


@pytest.fixture(autouse=True)
def stub_embedding_update(monkeypatch):
    calls = []
    async def fake_update(old, new):
        calls.append((old, new))
    from blackglass_server.routes import vault_routes
    from blackglass_server import db as db_mod
    monkeypatch.setattr(db_mod, "update_embedding_path", fake_update)
    return calls


def test_move_renames_file(client, vault):
    (vault / "src.md").write_text("hello")
    r = client.post("/vault/notes/src.md/move", json={"to": "dest.md", "rewrite_links": False})
    assert r.status_code == 200
    body = r.json()
    assert body["from"] == "src.md"
    assert body["to"] == "dest.md"
    assert (vault / "dest.md").read_text() == "hello"
    assert not (vault / "src.md").exists()


def test_move_with_link_rewrite(client, vault):
    (vault / "src.md").write_text("body")
    (vault / "ref.md").write_text("see [[src]] and [[src|alias]] and ![[src]] and [[src#h]]")
    r = client.post("/vault/notes/src.md/move", json={"to": "dest.md"})
    body = r.json()
    assert "ref.md" in body["rewrote_links_in"]
    text = (vault / "ref.md").read_text()
    assert text == "see [[dest]] and [[dest|alias]] and ![[dest]] and [[dest#h]]"


def test_move_dest_exists_409(client, vault):
    (vault / "src.md").write_text("a")
    (vault / "dest.md").write_text("b")
    r = client.post("/vault/notes/src.md/move", json={"to": "dest.md"})
    assert r.status_code == 409


def test_move_source_missing_404(client, vault):
    r = client.post("/vault/notes/ghost.md/move", json={"to": "dest.md"})
    assert r.status_code == 404


def test_move_stem_collision_flag(client, vault):
    (vault / "src.md").write_text("a")
    (vault / "Other").mkdir()
    (vault / "Other" / "src.md").write_text("b")
    r = client.post("/vault/notes/src.md/move", json={"to": "dest.md"})
    body = r.json()
    assert body["stem_collision"] is True
    assert "Other/src.md" in body["stem_collision_paths"]


def test_move_db_called(client, vault, stub_embedding_update):
    (vault / "src.md").write_text("a")
    client.post("/vault/notes/src.md/move", json={"to": "dest.md", "rewrite_links": False})
    assert ("src.md", "dest.md") in stub_embedding_update


def test_move_to_escape_400(client, vault):
    (vault / "src.md").write_text("a")
    r = client.post("/vault/notes/src.md/move", json={"to": "../escape.md"})
    assert r.status_code == 400
```

- [ ] **Step 9.4: Add the route**

Append to `blackglass-server/src/blackglass_server/routes/vault_routes.py`:

```python
@router.post("/notes/{path:path}/move")
async def move_note_route(path: str, body: dict) -> dict:
    from ..vault import move_note, rewrite_wikilinks, find_stem_collisions
    from ..db import update_embedding_path
    to = body.get("to", "")
    rewrite_links = body.get("rewrite_links", True)
    if not isinstance(to, str) or not to:
        raise HTTPException(status_code=400, detail="to must be a non-empty string")
    if to.endswith("/"):
        raise HTTPException(status_code=400, detail="to must not end with /")

    collisions = find_stem_collisions(settings.vault_path, path)
    try:
        move_note(settings.vault_path, path, to)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="source not found")
    except FileExistsError:
        raise HTTPException(status_code=409, detail="destination exists")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db_ok = True
    db_err = None
    try:
        await update_embedding_path(path, to)
    except Exception as exc:
        db_ok = False
        db_err = type(exc).__name__

    rewrote, errors = ([], [])
    if rewrite_links:
        rewrote, errors = rewrite_wikilinks(settings.vault_path, path, to)

    return {
        "from": path,
        "to": to,
        "rewrote_links_in": rewrote,
        "rewrite_errors": errors,
        "embedding_updated": db_ok,
        "db_error": db_err,
        "stem_collision": bool(collisions),
        "stem_collision_paths": collisions,
    }
```

- [ ] **Step 9.5: Run, confirm pass**

```
cd blackglass-server && uv run pytest tests/test_move.py -v
```
Expected: 7 passing.

- [ ] **Step 9.6: Commit**

```
git add blackglass-server/src/blackglass_server/vault.py \
        blackglass-server/src/blackglass_server/db.py \
        blackglass-server/src/blackglass_server/routes/vault_routes.py \
        blackglass-server/tests/test_move.py
git commit -m "feat(server): atomic move with wikilink rewrite"
```

---

## Task 10: Full-test pass + deploy

- [ ] **Step 10.1: Run full test suite**

```
cd blackglass-server && uv run pytest -v
```
Expected: all green.

- [ ] **Step 10.2: Smoke-test against live botvinnik (manual)**

In a separate shell:

```
ssh botvinnik
set -a; source /home/fishhouses/.config/blackglass/blackglass.env; set +a
curl -sS -H "X-API-Key: $BLACKGLASS_API_KEY" http://localhost:8083/vault/notes/beta.md/meta
curl -sS -X POST -H "X-API-Key: $BLACKGLASS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"paths": ["Middlegame Context.md"]}' \
  http://localhost:8083/vault/notes/batch
```

This step is manual — confirm the new routes respond on the deployed server before declaring done.

- [ ] **Step 10.3: Deploy**

```
./scripts/deploy.sh botvinnik
```

Run the smoke tests from 10.2 again.

- [ ] **Step 10.4: Final commit / push**

```
git push
```

---

## Self-review

**Spec coverage check:**

| Spec section | Plan task |
|---|---|
| §1 Snippets | Task 1 |
| §2 Batch read | Task 3 |
| §3 Changes | Task 6 |
| §4 Filter | Task 5 |
| §5 Replace PATCH | Task 7 |
| §6 Daily notes | Task 4 |
| §7 Meta | Task 2 |
| §8 Move | Task 9 |
| §9 Hybrid | Task 8 |
| Cross-cutting: BLACKGLASS_TZ | Task 0 |
| Cross-cutting: observability log lines | NOT IMPLEMENTED IN THIS PLAN — see note below |
| Cross-cutting: payload caps (PATCH 1 MiB, batch 50, snippet 1000) | Enforced in tasks 3, 7, 1 |
| Cross-cutting: idempotency | Implicit in op design |
| Cross-cutting: performance budgets | Not enforced in code (aspirational) |

**Observability log lines (Spec "Observability requirements"):**

The spec mandates structured INFO/WARN/ERROR log lines per endpoint with specific extras. The middleware from the prior session already emits `request_finished` with path/method/status/duration. The per-feature `extra` fields (e.g., `result_kind`, `result_count`, `replacements`, `stem_collision`) are NOT added in the plan above. To honor the spec, after each task add one line per handler:

```python
import logging
logger = logging.getLogger("blackglass.feature")
logger.info("feature_x", extra={"route": "<route>", "result_kind": "...", "result_count": ...})
```

Adding this verbatim to every handler would expand the plan substantially. Decision: track this as a separate, post-feature observability pass — Task 11 (not detailed here). All required telemetry shapes are documented in the spec, so a follow-on pass is mechanical.

**Placeholder scan:** No TODO/TBD strings. Every test has executable code. Every commit message is concrete.

**Type consistency check:**
- `read_note` returns dict with keys `path`, `content`, `frontmatter`, `body`, `wikilinks`, `tags` — used identically by batch read, daily notes, replace.
- `note_meta` returns a strict superset of meta fields used in tests.
- `update_embedding_path(old, new)` signature consistent between db.py and the move route.
- `list_files_filtered` return type `tuple[list[dict], int]` matches how the route deconstructs it.

**Open items deliberately deferred:**
- Observability per-handler extras (Task 11, mechanical).
- Performance budget enforcement / SLO instrumentation.
- Integration tests against a real Postgres + backwater. Unit tests use mocks; the smoke step (10.2) is the only end-to-end check.

## Execution Handoff

Plan complete and saved to `docs/plans/2026-05-30-agentic-extensions.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
