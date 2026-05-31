# Blackglass Server

Blackglass Server is an API-driven headless backend for Git-managed Markdown note vaults. It provides structured note manipulation, automatic wiki-link refactoring, git change tracking, and hybrid semantic-vector search for local or remote markdown repositories.

The server operates as a FastAPI application, interacting with a local Git repository (the vault), a PostgreSQL database with the pgvector extension for storing and querying text embeddings, and an external embeddings microservice (Backwater).

## Quick Start

### Prerequisites

* Python 3.12 or newer
* A local Git repository containing Markdown (`.md`) files
* PostgreSQL with the [pgvector](https://github.com/pgvector/pgvector) extension enabled
* A running instance of the Backwater embeddings service (configured to serve `nomic-ai/nomic-embed-text-v1.5`)

### Installation

Install the package and its dependencies using `pip` or `uv`:

```bash
pip install .
```

### Configuration

The server is configured via environment variables. Create an environment file or export the following variables:

```bash
# Vault & Security
export BLACKGLASS_VAULT_PATH="/path/to/your/markdown/vault"
export BLACKGLASS_API_KEY="your-secure-api-key"
export BLACKGLASS_PORT=8083

# Embedding Service (Backwater)
export BLACKGLASS_BACKWATER_URL="http://localhost:8080"

# Database Connection
export POSTGRES_USERNAME="postgres"
export POSTGRES_PASSWORD="your-postgres-password"
```

*Note: Database host discovery is handled dynamically through the `dbclients` package.*

### Start the Server

Run the server using Uvicorn:

```bash
uvicorn blackglass_server.main:app --host 127.0.0.1 --port 8083
```

Verify the server is running and connected to the vault:

```bash
curl -H "X-API-Key: your-secure-api-key" http://localhost:8083/health
```

Expected response:
```json
{
  "status": "ok",
  "vault": "/path/to/your/markdown/vault"
}
```

---

## Core Value Demonstration

This scenario demonstrates the server's primary capabilities: syncing new vault content, generating vector embeddings, running a hybrid search, and refactoring note paths.

### 1. Sync and Embed the Vault

The `/vault/sync` endpoint pulls the latest changes from the Git remote, parses updated or untracked Markdown files, extracts the first 2,000 characters of each document, requests embeddings from the Backwater service, and upserts them into PostgreSQL.

```bash
curl -X POST http://localhost:8083/vault/sync \
  -H "X-API-Key: your-secure-api-key"
```

Expected response:
```json
{
  "git": "Already up to date.",
  "files_checked": 142,
  "files_indexed": 12
}
```

### 2. Execute a Hybrid Search

The `/vault/hybrid-search` endpoint performs reciprocal rank fusion (RRF) on matches from both standard full-text search and cosine-similarity semantic vector search.

```bash
curl "http://localhost:8083/vault/hybrid-search?q=database+migrations&limit=2" \
  -H "X-API-Key: your-secure-api-key"
```

Expected response:
```json
{
  "results": [
    {
      "path": "technical/postgres-setup.md",
      "score": 0.032786,
      "sources": ["semantic", "text"],
      "text_rank": 1,
      "semantic_rank": 2,
      "snippet": "This document outlines how to initialize schemas and run pgvector migrations..."
    },
    {
      "path": "projects/active-schema.md",
      "score": 0.016393,
      "sources": ["semantic"],
      "text_rank": null,
      "semantic_rank": 1,
      "snippet": "We are currently shifting the active metadata layer to standard SQL tables..."
    }
  ],
  "degraded": null
}
```

### 3. Move a Note and Rewrite Backlinks

Moving a note updates its physical path on disk, updates its mapped path inside the database embeddings table, identifies other documents containing WikiLinks (`[[Old Note Name]]` or `[[Old Note Name|Alias]]`), and rewrites those links inline to match the new name.

```bash
curl -X POST http://localhost:8083/vault/notes/technical/postgres-setup.md/move \
  -H "X-API-Key: your-secure-api-key" \
  -H "Content-Type: application/json" \
  -d '{"to": "database/postgres-setup.md", "rewrite_links": true}'
```

Expected response:
```json
{
  "from": "technical/postgres-setup.md",
  "to": "database/postgres-setup.md",
  "rewrote_links_in": [
    "projects/active-schema.md",
    "technical/index.md"
  ],
  "rewrite_errors": [],
  "embedding_updated": true,
  "stem_collision": false,
  "stem_collision_paths": []
}
```

---

## Architectural Design

```
                     +---------------------------------------+
                     |           Blackglass Server           |
                     |               (FastAPI)               |
                     +---+---------------+---------------+---+
                         |               |               |
                         v               v               v
                +--------+--------+  +---+----+  +-------+-------+
                | Local Git Vault |  | Postgres|  |   Backwater   |
                |  (.md files)    |  |  +      |  |  Embeddings   |
                |                 |  |vector  |  |    (HTTP)     |
                +-----------------+  +--------+  +---------------+
```

* **Git Vault**: The source of truth. File read, write, and deletion operations interact directly with this directory. History is tracked natively using the system's `git` binary.
* **PostgreSQL + pgvector**: Stores document hashes and dense vector representations (`vector(768)`) generated from note contents. Powering both semantic and hybrid search queries.
* **Backwater Service**: Handles translation of raw Markdown text into vector embeddings using the `nomic-ai/nomic-embed-text-v1.5` model.

---

## Essential API Reference

### Note Operations

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/vault/notes/{path}` | Retrieves a note, parsing YAML frontmatter, content body, wikilinks, and tags. |
| `POST` | `/vault/notes` | Creates a new note. Fails with a `409 Conflict` if the file already exists. |
| `PUT` | `/vault/notes/{path}` | Overwrites or creates a note at the target path. |
| `PATCH` | `/vault/notes/{path}` | Modifies a note's contents or frontmatter using localized operations. |
| `DELETE` | `/vault/notes/{path}` | Deletes the specified note. |
| `POST` | `/vault/notes/batch` | Reads multiple note paths in a single roundtrip (maximum 50 paths). |

#### JSON Patch Schema (`PATCH /vault/notes/{path}`)
Allows safe modification without rewriting entire files. Supported operations:

```json
{
  "op": "append" | "prepend" | "set_frontmatter" | "replace",
  "content": "string",            // Required for append / prepend
  "key": "frontmatter_key",       // Required for set_frontmatter
  "value": "frontmatter_value",   // Required for set_frontmatter
  "old": "exact text to match",   // Required for replace
  "new": "replacement text",      // Required for replace
  "replace_all": false            // Optional for replace (default: false)
}
```

### Search & Discovery

| Method | Endpoint | Query Parameters | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/vault/files` | `tag`, `fm.<key>`, `path_glob`, `limit` | Lists files in the vault filtered by tags, frontmatter variables, or path patterns. |
| `GET` | `/vault/search` | `q`, `snippet_chars` | Performs standard substring searches. |
| `GET` | `/vault/semantic-search` | `q`, `limit`, `snippet_chars` | Executes cosine-similarity searches using vector embeddings. |
| `GET` | `/vault/hybrid-search` | `q`, `limit`, `snippet_chars`, `k` | Combines results of full-text and semantic queries using Reciprocal Rank Fusion. |
| `GET` | `/vault/backlinks/{path}` | None | Discovers all notes containing WikiLinks to the target path stem. |

### Periodic / Daily Notes

The server identifies periodic notes formatted as `YYYY-MM-DD.md` in the root of the vault.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/vault/periodic` | Lists all daily notes inside the vault ordered chronologically. |
| `GET` | `/vault/periodic/today` | Resolves and returns the daily note for the configured timezone (`BLACKGLASS_TZ`). Creates the file if it does not exist. |
| `GET` | `/vault/periodic/yesterday` | Resolves, creates (if missing), and returns yesterday's note. |
| `GET` | `/vault/periodic/by-date/{date_str}` | Retrieves or creates a daily note for the specified date string (format: `YYYY-MM-DD`). |

### Diagnostics & Monitoring

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/status` | Returns process details, uptime, indexed document counts, and last synchronization details. |
| `GET` | `/logs/last` | Fetches the last $N$ application log events from the in-memory ring buffer (up to 200 events). |
| `GET` | `/logs/journal` | Retrieves system logs directly from the systemd unit `blackglass` via journalctl. |
