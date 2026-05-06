# Blackglass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI HTTP server + Click CLI that expose an Obsidian vault over REST for agentic access.

**Architecture:** Server reads/writes the vault as plain `.md` files, parses frontmatter and wikilinks, and supports full-text and semantic (pgvector) search. Semantic embeddings are generated via the Backwater Headwater server (`POST /conduit/embeddings/quick`, model `nomic-ai/nomic-embed-text-v1.5`, 768 dims) and stored in Postgres. The CLI is a thin httpx wrapper with `--json` flag for agent-friendly output.

**Tech Stack:** FastAPI, uvicorn, pydantic-settings, httpx, asyncpg, pgvector, PyYAML, Click, uv workspace

---

## File Map

```
blackglass/
  pyproject.toml                          # uv workspace root
  blackglass-server/
    pyproject.toml
    src/blackglass_server/
      __init__.py
      main.py                             # FastAPI app, lifespan, router registration
      config.py                           # Settings (pydantic-settings)
      auth.py                             # X-API-Key dependency
      text_utils.py                       # frontmatter parsing, wikilink extraction (pure)
      vault.py                            # all vault file operations
      db.py                               # asyncpg pool + pgvector schema init
      embeddings.py                       # Backwater httpx client
      routes/
        __init__.py
        notes.py                          # GET/POST/PUT/PATCH/DELETE /vault/notes/{path:path}
        vault_routes.py                   # /vault/files, /vault/tags, /vault/backlinks, /vault/periodic
        search.py                         # /vault/search, /vault/semantic-search
        sync.py                           # POST /vault/sync
    tests/
      conftest.py
      test_text_utils.py
      test_vault.py
  blackglass-client/
    pyproject.toml
    src/blackglass_client/
      __init__.py
      client.py                           # httpx wrapper, reads BLACKGLASS_URL + BLACKGLASS_API_KEY
      cli/
        __init__.py
        main.py                           # click group "blackglass"
        notes.py                          # blackglass notes get/create/update/patch/delete
        vault_cmds.py                     # blackglass vault files/tags/backlinks/periodic/sync
        search_cmds.py                    # blackglass search text/semantic
  scripts/
    deploy.sh                             # rsync + uv sync on botvinnik
```

---

## Environment Variables

**Server (botvinnik):**
- `BLACKGLASS_VAULT_PATH` — path to vault (default: `$MORPHY`, must be set)
- `BLACKGLASS_API_KEY` — auth token
- `BLACKGLASS_PORT` — port (default: `8083`)
- `BLACKGLASS_BACKWATER_URL` — Backwater base URL (default: `http://localhost:8080`)
- `POSTGRES_PASSWORD` — required by dbclients
- `POSTGRES_USERNAME` — optional (default: `bianders`)

**Client (any host):**
- `BLACKGLASS_URL` — server URL (default: `http://172.16.0.3:8083`)
- `BLACKGLASS_API_KEY` — auth token

---

## Task 1: Workspace Scaffold

**Files:**
- Create: `blackglass/pyproject.toml`
- Create: `blackglass-server/pyproject.toml`
- Create: `blackglass-client/pyproject.toml`
- Create: all `__init__.py` stubs

- [ ] **Step 1: Create workspace root**

```toml
# blackglass/pyproject.toml
[tool.uv.workspace]
members = ["blackglass-server", "blackglass-client"]
```

- [ ] **Step 2: Create server package**

```toml
# blackglass/blackglass-server/pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "blackglass-server"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "pydantic-settings",
    "httpx",
    "asyncpg",
    "pgvector",
    "pyyaml",
    "dbclients",
]

[tool.uv.sources]
dbclients = { git = "https://github.com/acesanderson/database-clients.git" }

[tool.hatch.build.targets.wheel]
packages = ["src/blackglass_server"]
```

> **Dev override on MacBook:** run `uv add --editable /Users/bianders/Brian_Code/dbclients-project` once to override with local path.

- [ ] **Step 3: Create client package**

```toml
# blackglass/blackglass-client/pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "blackglass-client"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "click",
    "httpx",
]

[project.scripts]
blackglass = "blackglass_client.cli.main:cli"

[tool.hatch.build.targets.wheel]
packages = ["src/blackglass_client"]
```

- [ ] **Step 4: Create all directory structure and empty `__init__.py` files**

```bash
cd /Users/bianders/vibe/blackglass
mkdir -p blackglass-server/src/blackglass_server/routes
mkdir -p blackglass-server/tests
mkdir -p blackglass-client/src/blackglass_client/cli
mkdir -p scripts docs/plans

touch blackglass-server/src/blackglass_server/__init__.py
touch blackglass-server/src/blackglass_server/routes/__init__.py
touch blackglass-client/src/blackglass_client/__init__.py
touch blackglass-client/src/blackglass_client/cli/__init__.py
touch blackglass-server/tests/__init__.py
```

- [ ] **Step 5: Install workspace**

```bash
cd /Users/bianders/vibe/blackglass
uv sync
```

Expected: resolves all deps, creates `.venv` at workspace root.

- [ ] **Step 6: Commit**

```bash
git init
git add .
git commit -m "feat(scaffold): uv workspace with server and client packages"
```

---

## Task 2: Config + Auth

**Files:**
- Create: `blackglass-server/src/blackglass_server/config.py`
- Create: `blackglass-server/src/blackglass_server/auth.py`

- [ ] **Step 1: Write config**

```python
# src/blackglass_server/config.py
from __future__ import annotations
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    vault_path: Path
    api_key: str
    port: int = 8083
    backwater_url: str = "http://localhost:8080"

    model_config = {"env_prefix": "BLACKGLASS_"}


settings = Settings()
```

- [ ] **Step 2: Write auth dependency**

```python
# src/blackglass_server/auth.py
from __future__ import annotations
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from .config import settings

_header = APIKeyHeader(name="X-API-Key")


def require_api_key(key: str = Security(_header)) -> str:
    if key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return key
```

- [ ] **Step 3: Commit**

```bash
git add blackglass-server/src/blackglass_server/config.py \
        blackglass-server/src/blackglass_server/auth.py
git commit -m "feat(server): config and API key auth"
```

---

## Task 3: text_utils (pure, fully tested)

**Files:**
- Create: `blackglass-server/src/blackglass_server/text_utils.py`
- Create: `blackglass-server/tests/conftest.py`
- Create: `blackglass-server/tests/test_text_utils.py`

- [ ] **Step 1: Write failing tests**

```python
# blackglass-server/tests/test_text_utils.py
from blackglass_server.text_utils import split_frontmatter, extract_wikilinks, extract_tags


def test_split_frontmatter_with_yaml():
    text = "---\ntitle: Test\ntags: [a, b]\n---\nBody here."
    fm, body = split_frontmatter(text)
    assert fm == {"title": "Test", "tags": ["a", "b"]}
    assert body == "Body here."


def test_split_frontmatter_none():
    text = "No frontmatter here."
    fm, body = split_frontmatter(text)
    assert fm == {}
    assert body == "No frontmatter here."


def test_extract_wikilinks():
    body = "See [[Note One]] and [[Note Two|display]]."
    links = extract_wikilinks(body)
    assert links == ["Note One", "Note Two"]


def test_extract_wikilinks_empty():
    assert extract_wikilinks("No links here.") == []


def test_extract_tags_from_frontmatter():
    fm = {"tags": ["alpha", "beta"]}
    assert extract_tags(fm) == ["alpha", "beta"]


def test_extract_tags_string_value():
    fm = {"tags": "solo"}
    assert extract_tags(fm) == ["solo"]


def test_extract_tags_missing():
    assert extract_tags({}) == []
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/bianders/vibe/blackglass
uv run --package blackglass-server pytest blackglass-server/tests/test_text_utils.py -v
```

Expected: ImportError or AttributeError (module not yet written).

- [ ] **Step 3: Write implementation**

```python
# src/blackglass_server/text_utils.py
from __future__ import annotations
import re
import yaml

_FM_RE = re.compile(r"^---[ \t]*\n(.*?)\n---[ \t]*\n?", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def split_frontmatter(text: str) -> tuple[dict, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    fm = yaml.safe_load(m.group(1)) or {}
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
```

- [ ] **Step 4: Run tests — verify pass**

```bash
uv run --package blackglass-server pytest blackglass-server/tests/test_text_utils.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add blackglass-server/src/blackglass_server/text_utils.py \
        blackglass-server/tests/test_text_utils.py
git commit -m "feat(server): text_utils — frontmatter, wikilinks, tags"
```

---

## Task 4: vault.py (file operations, tested with tmp_path)

**Files:**
- Create: `blackglass-server/src/blackglass_server/vault.py`
- Create: `blackglass-server/tests/test_vault.py`

- [ ] **Step 1: Write failing tests**

```python
# blackglass-server/tests/test_vault.py
import pytest
from pathlib import Path
from blackglass_server.vault import (
    read_note, write_note, delete_note, list_files,
    compute_backlinks, list_tags, list_periodic_notes,
)


@pytest.fixture
def vault(tmp_path):
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "Note A.md").write_text("---\ntags: [foo]\n---\nSee [[Note B]].")
    (tmp_path / "Note B.md").write_text("No frontmatter.")
    (tmp_path / "2024-01-15.md").write_text("Daily note.")
    return tmp_path


def test_read_note(vault):
    note = read_note(vault, "Note A.md")
    assert note["frontmatter"] == {"tags": ["foo"]}
    assert "See [[Note B]]" in note["body"]
    assert note["wikilinks"] == ["Note B"]
    assert note["tags"] == ["foo"]


def test_read_note_missing(vault):
    with pytest.raises(FileNotFoundError):
        read_note(vault, "Ghost.md")


def test_write_and_read(vault):
    write_note(vault, "New.md", "---\ntitle: New\n---\nHello.")
    note = read_note(vault, "New.md")
    assert note["frontmatter"]["title"] == "New"


def test_delete_note(vault):
    delete_note(vault, "Note B.md")
    assert not (vault / "Note B.md").exists()


def test_delete_missing(vault):
    with pytest.raises(FileNotFoundError):
        delete_note(vault, "Ghost.md")


def test_list_files(vault):
    files = list_files(vault)
    paths = [f["path"] for f in files]
    assert "Note A.md" in paths
    assert "Note B.md" in paths


def test_compute_backlinks(vault):
    bl = compute_backlinks(vault, "Note B.md")
    assert "Note A.md" in bl


def test_list_tags(vault):
    tags = list_tags(vault)
    assert any(t["tag"] == "foo" for t in tags)


def test_list_periodic_notes(vault):
    periodic = list_periodic_notes(vault)
    assert any(p["path"] == "2024-01-15.md" for p in periodic)
```

- [ ] **Step 2: Run tests — verify fail**

```bash
uv run --package blackglass-server pytest blackglass-server/tests/test_vault.py -v
```

- [ ] **Step 3: Write implementation**

```python
# src/blackglass_server/vault.py
from __future__ import annotations
import re
from pathlib import Path
from .text_utils import split_frontmatter, extract_wikilinks, extract_tags

_PERIODIC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")


def _resolve(vault_path: Path, rel_path: str) -> Path:
    p = (vault_path / rel_path).resolve()
    if not str(p).startswith(str(vault_path.resolve())):
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
```

- [ ] **Step 4: Run tests — verify pass**

```bash
uv run --package blackglass-server pytest blackglass-server/tests/test_vault.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add blackglass-server/src/blackglass_server/vault.py \
        blackglass-server/tests/test_vault.py
git commit -m "feat(server): vault file operations with tests"
```

---

## Task 5: FastAPI App + Note CRUD Routes

**Files:**
- Create: `blackglass-server/src/blackglass_server/main.py`
- Create: `blackglass-server/src/blackglass_server/routes/notes.py`

- [ ] **Step 1: Write main.py**

```python
# src/blackglass_server/main.py
from __future__ import annotations
from fastapi import FastAPI
from .config import settings
from .routes import notes, vault_routes, search, sync

app = FastAPI(title="blackglass", version="0.1.0")
app.include_router(notes.router)
app.include_router(vault_routes.router)
app.include_router(search.router)
app.include_router(sync.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "vault": str(settings.vault_path)}
```

- [ ] **Step 2: Write note CRUD routes**

```python
# src/blackglass_server/routes/notes.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from ..auth import require_api_key
from ..config import settings
from ..vault import read_note, write_note, delete_note
from ..text_utils import split_frontmatter

router = APIRouter(prefix="/vault/notes", dependencies=[Depends(require_api_key)])


class NoteCreate(BaseModel):
    content: str


class NotePatch(BaseModel):
    op: str           # "append" | "prepend" | "set_frontmatter"
    content: str | None = None
    key: str | None = None
    value: str | None = None


@router.get("/{path:path}")
def get_note(path: str) -> dict:
    try:
        return read_note(settings.vault_path, path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_note(path: str, body: NoteCreate) -> dict:
    full = settings.vault_path / path
    if full.exists():
        raise HTTPException(status_code=409, detail=f"Note already exists: {path}")
    write_note(settings.vault_path, path, body.content)
    return read_note(settings.vault_path, path)


@router.put("/{path:path}")
def replace_note(path: str, body: NoteCreate) -> dict:
    write_note(settings.vault_path, path, body.content)
    return read_note(settings.vault_path, path)


@router.patch("/{path:path}")
def patch_note(path: str, body: NotePatch) -> dict:
    try:
        note = read_note(settings.vault_path, path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")

    if body.op == "append":
        new_content = note["content"].rstrip() + "\n" + (body.content or "")
    elif body.op == "prepend":
        fm, b = split_frontmatter(note["content"])
        # re-insert frontmatter then prepend to body
        fm_block = f"---\n" + _dict_to_yaml(fm) + "---\n" if fm else ""
        new_content = fm_block + (body.content or "") + "\n" + b
    elif body.op == "set_frontmatter":
        import yaml
        fm, b = split_frontmatter(note["content"])
        fm[body.key] = body.value
        new_content = "---\n" + yaml.dump(fm, default_flow_style=False) + "---\n" + b
    else:
        raise HTTPException(status_code=422, detail=f"Unknown op: {body.op}")

    write_note(settings.vault_path, path, new_content)
    return read_note(settings.vault_path, path)


@router.delete("/{path:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note_route(path: str) -> None:
    try:
        delete_note(settings.vault_path, path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")


def _dict_to_yaml(d: dict) -> str:
    import yaml
    return yaml.dump(d, default_flow_style=False) if d else ""
```

- [ ] **Step 3: Smoke test the app starts**

```bash
cd /Users/bianders/vibe/blackglass
BLACKGLASS_VAULT_PATH=/Users/bianders/morphy BLACKGLASS_API_KEY=test \
  uv run --package blackglass-server uvicorn blackglass_server.main:app --port 8083
```

Expected: starts without error, `GET /health` returns `{"status": "ok"}`.

- [ ] **Step 4: Commit**

```bash
git add blackglass-server/src/blackglass_server/main.py \
        blackglass-server/src/blackglass_server/routes/notes.py
git commit -m "feat(server): FastAPI app and note CRUD routes"
```

---

## Task 6: Vault Info + Search Routes

**Files:**
- Create: `blackglass-server/src/blackglass_server/routes/vault_routes.py`
- Create: `blackglass-server/src/blackglass_server/routes/search.py`

- [ ] **Step 1: Write vault info routes**

```python
# src/blackglass_server/routes/vault_routes.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from ..auth import require_api_key
from ..config import settings
from ..vault import list_files, list_tags, compute_backlinks, list_periodic_notes

router = APIRouter(prefix="/vault", dependencies=[Depends(require_api_key)])


@router.get("/files")
def get_files() -> list[dict]:
    return list_files(settings.vault_path)


@router.get("/tags")
def get_tags() -> list[dict]:
    return list_tags(settings.vault_path)


@router.get("/periodic")
def get_periodic() -> list[dict]:
    return list_periodic_notes(settings.vault_path)


@router.get("/backlinks/{path:path}")
def get_backlinks(path: str) -> dict:
    bl = compute_backlinks(settings.vault_path, path)
    return {"path": path, "backlinks": bl}
```

- [ ] **Step 2: Write full-text search route**

```python
# src/blackglass_server/routes/search.py
from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from ..auth import require_api_key
from ..config import settings
from ..vault import fulltext_search

router = APIRouter(prefix="/vault", dependencies=[Depends(require_api_key)])


@router.get("/search")
def text_search(q: str = Query(..., min_length=1)) -> list[dict]:
    return fulltext_search(settings.vault_path, q)


# Semantic search route added in Task 8 after db/embeddings are wired up
```

- [ ] **Step 3: Register routers in main.py** — update the import list (vault_routes and search are already imported in Task 5's main.py stub; verify they're present).

- [ ] **Step 4: Commit**

```bash
git add blackglass-server/src/blackglass_server/routes/vault_routes.py \
        blackglass-server/src/blackglass_server/routes/search.py
git commit -m "feat(server): vault info and full-text search routes"
```

---

## Task 7: DB + Embeddings

**Files:**
- Create: `blackglass-server/src/blackglass_server/db.py`
- Create: `blackglass-server/src/blackglass_server/embeddings.py`

- [ ] **Step 1: Write db.py — pool init and schema**

```python
# src/blackglass_server/db.py
from __future__ import annotations
import asyncpg
from dbclients import get_network_context

_pool: asyncpg.Pool | None = None
_EMBED_DIM = 768


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_pool() first")
    return _pool


async def init_pool() -> None:
    global _pool
    ctx = get_network_context()
    import os
    _pool = await asyncpg.create_pool(
        host=ctx.preferred_host,
        port=5432,
        database="blackglass",
        user=os.environ.get("POSTGRES_USERNAME", "bianders"),
        password=os.environ["POSTGRES_PASSWORD"],
    )
    await _ensure_schema()


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def _ensure_schema() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS vault_embeddings (
                path TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                embedding vector({_EMBED_DIM}),
                indexed_at TIMESTAMPTZ DEFAULT now()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS vault_embeddings_embedding_idx
            ON vault_embeddings USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """)


async def upsert_embedding(path: str, content_hash: str, embedding: list[float]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO vault_embeddings (path, content_hash, embedding, indexed_at)
            VALUES ($1, $2, $3::vector, now())
            ON CONFLICT (path) DO UPDATE
            SET content_hash = EXCLUDED.content_hash,
                embedding = EXCLUDED.embedding,
                indexed_at = now()
        """, path, content_hash, str(embedding))


async def get_indexed_hashes() -> dict[str, str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT path, content_hash FROM vault_embeddings")
        return {r["path"]: r["content_hash"] for r in rows}


async def semantic_search(query_embedding: list[float], limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT path, 1 - (embedding <=> $1::vector) AS score
            FROM vault_embeddings
            ORDER BY embedding <=> $1::vector
            LIMIT $2
        """, str(query_embedding), limit)
        return [{"path": r["path"], "score": float(r["score"])} for r in rows]
```

- [ ] **Step 2: Wire pool into app lifespan**

```python
# src/blackglass_server/main.py  (full replacement)
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .config import settings
from .db import init_pool, close_pool
from .routes import notes, vault_routes, search, sync


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="blackglass", version="0.1.0", lifespan=lifespan)
app.include_router(notes.router)
app.include_router(vault_routes.router)
app.include_router(search.router)
app.include_router(sync.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "vault": str(settings.vault_path)}
```

- [ ] **Step 3: Write embeddings.py**

```python
# src/blackglass_server/embeddings.py
from __future__ import annotations
import httpx
from .config import settings

_MODEL = "nomic-ai/nomic-embed-text-v1.5"


async def embed_text(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.backwater_url}/conduit/embeddings/quick",
            json={"query": text, "model": _MODEL},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


async def embed_batch(texts: list[str], ids: list[str]) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.backwater_url}/conduit/embeddings",
            json={
                "model": _MODEL,
                "batch": {"ids": ids, "documents": texts, "embeddings": None, "metadatas": {}},
            },
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]
```

- [ ] **Step 4: Commit**

```bash
git add blackglass-server/src/blackglass_server/db.py \
        blackglass-server/src/blackglass_server/embeddings.py \
        blackglass-server/src/blackglass_server/main.py
git commit -m "feat(server): asyncpg pool, pgvector schema, Backwater embeddings client"
```

---

## Task 8: Sync + Semantic Search Routes

**Files:**
- Create: `blackglass-server/src/blackglass_server/routes/sync.py`
- Modify: `blackglass-server/src/blackglass_server/routes/search.py`

- [ ] **Step 1: Write sync route**

```python
# src/blackglass_server/routes/sync.py
from __future__ import annotations
import hashlib
import subprocess
from fastapi import APIRouter, Depends, BackgroundTasks
from ..auth import require_api_key
from ..config import settings
from ..vault import list_files
from ..db import get_indexed_hashes, upsert_embedding
from ..embeddings import embed_batch

router = APIRouter(prefix="/vault", dependencies=[Depends(require_api_key)])


async def _reindex() -> dict:
    # git pull
    result = subprocess.run(
        ["git", "pull", "--ff-only"],
        cwd=settings.vault_path,
        capture_output=True, text=True,
    )

    files = list_files(settings.vault_path)
    indexed = await get_indexed_hashes()

    to_index = []
    for f in files:
        path = f["path"]
        content = (settings.vault_path / path).read_text(encoding="utf-8", errors="ignore")
        h = hashlib.sha256(content.encode()).hexdigest()
        if indexed.get(path) != h:
            to_index.append((path, content, h))

    # embed in batches of 32
    batch_size = 32
    indexed_count = 0
    for i in range(0, len(to_index), batch_size):
        batch = to_index[i:i + batch_size]
        paths = [b[0] for b in batch]
        texts = [b[1] for b in batch]
        hashes = [b[2] for b in batch]
        embeddings = await embed_batch(texts, paths)
        for path, h, emb in zip(paths, hashes, embeddings):
            await upsert_embedding(path, h, emb)
            indexed_count += 1

    return {
        "git": result.stdout.strip(),
        "files_checked": len(files),
        "files_indexed": indexed_count,
    }


@router.post("/sync")
async def sync_vault(background_tasks: BackgroundTasks) -> dict:
    # Run sync inline (not background) so client knows when it's done
    return await _reindex()
```

- [ ] **Step 2: Add semantic search to search.py**

```python
# Add to src/blackglass_server/routes/search.py (append to existing file)
from ..db import semantic_search as db_semantic_search
from ..embeddings import embed_text


@router.get("/semantic-search")
async def semantic_search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)) -> list[dict]:
    embedding = await embed_text(q)
    return await db_semantic_search(embedding, limit)
```

- [ ] **Step 3: Commit**

```bash
git add blackglass-server/src/blackglass_server/routes/sync.py \
        blackglass-server/src/blackglass_server/routes/search.py
git commit -m "feat(server): sync route with incremental re-indexing and semantic search"
```

---

## Task 9: CLI Client

**Files:**
- Create: `blackglass-client/src/blackglass_client/client.py`
- Create: `blackglass-client/src/blackglass_client/cli/main.py`
- Create: `blackglass-client/src/blackglass_client/cli/notes.py`
- Create: `blackglass-client/src/blackglass_client/cli/vault_cmds.py`
- Create: `blackglass-client/src/blackglass_client/cli/search_cmds.py`

- [ ] **Step 1: Write HTTP client**

```python
# src/blackglass_client/client.py
from __future__ import annotations
import json as _json
import os
import httpx

_DEFAULT_URL = "http://172.16.0.3:8083"


def _client() -> httpx.Client:
    url = os.environ.get("BLACKGLASS_URL", _DEFAULT_URL)
    key = os.environ.get("BLACKGLASS_API_KEY", "")
    return httpx.Client(base_url=url, headers={"X-API-Key": key}, timeout=60.0)


def request(method: str, path: str, **kwargs) -> dict | list:
    with _client() as c:
        resp = c.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 2: Write CLI main group**

```python
# src/blackglass_client/cli/main.py
from __future__ import annotations
import click
from .notes import notes
from .vault_cmds import vault
from .search_cmds import search


@click.group()
def cli():
    """Blackglass — Obsidian vault over HTTP."""


cli.add_command(notes)
cli.add_command(vault)
cli.add_command(search)
```

- [ ] **Step 3: Write notes commands**

```python
# src/blackglass_client/cli/notes.py
from __future__ import annotations
import json
import sys
import click
from ..client import request


@click.group()
def notes():
    """Note CRUD operations."""


def _out(data, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        if isinstance(data, dict):
            for k, v in data.items():
                click.echo(f"{k}: {v}")
        else:
            click.echo(data)


@notes.command("get")
@click.argument("path")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON")
def get_note(path: str, as_json: bool) -> None:
    """Get a note by vault-relative path."""
    data = request("GET", f"/vault/notes/{path}")
    _out(data, as_json)


@notes.command("create")
@click.argument("path")
@click.option("--content", required=True, help="Note content (markdown)")
@click.option("--json", "as_json", is_flag=True)
def create_note(path: str, content: str, as_json: bool) -> None:
    """Create a new note."""
    data = request("POST", "/vault/notes", params={"path": path}, json={"content": content})
    _out(data, as_json)


@notes.command("update")
@click.argument("path")
@click.option("--content", required=True)
@click.option("--json", "as_json", is_flag=True)
def update_note(path: str, content: str, as_json: bool) -> None:
    """Replace a note's content."""
    data = request("PUT", f"/vault/notes/{path}", json={"content": content})
    _out(data, as_json)


@notes.command("append")
@click.argument("path")
@click.argument("content")
@click.option("--json", "as_json", is_flag=True)
def append_note(path: str, content: str, as_json: bool) -> None:
    """Append content to a note."""
    data = request("PATCH", f"/vault/notes/{path}", json={"op": "append", "content": content})
    _out(data, as_json)


@notes.command("set-frontmatter")
@click.argument("path")
@click.argument("key")
@click.argument("value")
@click.option("--json", "as_json", is_flag=True)
def set_frontmatter(path: str, key: str, value: str, as_json: bool) -> None:
    """Set a frontmatter field on a note."""
    data = request("PATCH", f"/vault/notes/{path}", json={"op": "set_frontmatter", "key": key, "value": value})
    _out(data, as_json)


@notes.command("delete")
@click.argument("path")
def delete_note(path: str) -> None:
    """Delete a note."""
    request("DELETE", f"/vault/notes/{path}")
    click.echo(f"Deleted: {path}")
```

- [ ] **Step 4: Write vault commands**

```python
# src/blackglass_client/cli/vault_cmds.py
from __future__ import annotations
import json
import click
from ..client import request


def _out(data, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        if isinstance(data, list):
            for item in data:
                click.echo(item if isinstance(item, str) else json.dumps(item))
        else:
            click.echo(json.dumps(data, indent=2))


@click.group()
def vault():
    """Vault-level operations."""


@vault.command("files")
@click.option("--json", "as_json", is_flag=True)
def files(as_json: bool) -> None:
    """List all notes in the vault."""
    _out(request("GET", "/vault/files"), as_json)


@vault.command("tags")
@click.option("--json", "as_json", is_flag=True)
def tags(as_json: bool) -> None:
    """List all tags with counts."""
    _out(request("GET", "/vault/tags"), as_json)


@vault.command("periodic")
@click.option("--json", "as_json", is_flag=True)
def periodic(as_json: bool) -> None:
    """List periodic (daily) notes."""
    _out(request("GET", "/vault/periodic"), as_json)


@vault.command("backlinks")
@click.argument("path")
@click.option("--json", "as_json", is_flag=True)
def backlinks(path: str, as_json: bool) -> None:
    """List notes that link to PATH."""
    _out(request("GET", f"/vault/backlinks/{path}"), as_json)


@vault.command("sync")
def sync() -> None:
    """Git pull and re-index changed notes."""
    result = request("POST", "/vault/sync")
    click.echo(f"git: {result.get('git', '')}")
    click.echo(f"checked: {result['files_checked']}  indexed: {result['files_indexed']}")
```

- [ ] **Step 5: Write search commands**

```python
# src/blackglass_client/cli/search_cmds.py
from __future__ import annotations
import json
import click
from ..client import request


def _out(data, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        for item in data:
            click.echo(f"  {item['path']}")
            if "excerpt" in item:
                click.echo(f"    {item['excerpt'][:120]}")
            if "score" in item:
                click.echo(f"    score: {item['score']:.3f}")


@click.group()
def search():
    """Search the vault."""


@search.command("text")
@click.argument("query")
@click.option("--json", "as_json", is_flag=True)
def text_search(query: str, as_json: bool) -> None:
    """Full-text search across all notes."""
    results = request("GET", "/vault/search", params={"q": query})
    _out(results, as_json)


@search.command("semantic")
@click.argument("query")
@click.option("--limit", default=10, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def semantic_search(query: str, limit: int, as_json: bool) -> None:
    """Semantic (embedding) search across indexed notes."""
    results = request("GET", "/vault/semantic-search", params={"q": query, "limit": limit})
    _out(results, as_json)
```

- [ ] **Step 6: Install CLI and smoke test**

```bash
cd /Users/bianders/vibe/blackglass
uv pip install -e blackglass-client
blackglass --help
```

Expected: shows `notes`, `vault`, `search` subcommands.

- [ ] **Step 7: Commit**

```bash
git add blackglass-client/
git commit -m "feat(client): Click CLI with notes, vault, and search commands"
```

---

## Task 10: Deploy Script

**Files:**
- Create: `scripts/deploy.sh`

- [ ] **Step 1: Write deploy script**

```bash
#!/usr/bin/env bash
# scripts/deploy.sh — deploy blackglass to botvinnik
set -euo pipefail

REMOTE="fishhouses@172.16.0.3"
REMOTE_DIR="~/services/blackglass"
BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "==> Pushing $BRANCH to GitHub"
git push origin "$BRANCH"

echo "==> Pulling on botvinnik"
ssh -p 2222 "$REMOTE" "
  set -euo pipefail
  cd $REMOTE_DIR
  git pull --ff-only
  cd blackglass-server
  uv sync
  echo 'Deploy complete.'
"

echo "==> Done. Restart the blackglass systemd service if needed:"
echo "    ssh -p 2222 $REMOTE 'sudo systemctl restart blackglass'"
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x scripts/deploy.sh
git add scripts/deploy.sh
git commit -m "feat(deploy): deploy script for botvinnik"
```

---

## Self-Review

**Spec coverage:**
- Note CRUD (GET/POST/PUT/PATCH/DELETE) — Task 5 ✓
- `/vault/files` — Task 6 ✓
- `/vault/tags` — Task 6 ✓
- `/vault/periodic` — Task 6 ✓
- `/vault/backlinks/{path}` — Task 6 ✓
- `/vault/search` (full-text) — Task 6 ✓
- `/vault/semantic-search` — Task 8 ✓
- `/vault/sync` (git pull + re-index) — Task 8 ✓
- API key auth — Task 2 ✓
- pgvector storage — Task 7 ✓
- Backwater (nomic-embed-text-v1.5) — Task 7 ✓
- Click CLI with --json flag — Task 9 ✓
- Deploy script — Task 10 ✓

**Gaps / notes:**
- The `blackglass` database must be created on Caruana before first run: `createdb blackglass` (or `psql -c "CREATE DATABASE blackglass"`)
- On botvinnik, `$MORPHY` must point to the git-cloned vault directory
- The IVFFlat index in `_ensure_schema` requires at least ~100 rows before it's useful; small vaults will still work via sequential scan

**Type consistency check:** `embed_batch` returns `list[list[float]]`; `upsert_embedding` accepts `list[float]` — the zip loop in sync.py correctly unpacks one embedding per path. ✓
