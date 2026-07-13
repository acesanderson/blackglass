# CLI Full Coverage

**Status:** DONE
**Source:** `docs/specs/2026-05-31-cli-full-coverage.md`

---

## Goal

Bring `blackglass-client` to 100% endpoint and parameter fidelity with the server. Every server route reachable via a CLI verb; every query param and body field that affects output reachable via a CLI flag. The CLI is the primary agentic interface to blackglass — agents must be able to do anything the HTTP API offers without falling back to raw `curl`.

## Interface / Scope

### What the user/system sees

A `blackglass` CLI with four command groups:

- **`notes`** — 11 verbs: `get`, `meta`, `create`, `update`, `append`, `prepend`, `set-frontmatter`, `replace`, `delete`, `batch`, `move`
- **`vault`** — 12 verbs: `files`, `tags`, `backlinks`, `sync`, `changes`, `periodic list`, `periodic today`, `periodic yesterday`, `periodic on`, `periodic append-today`, `periodic patch-today`
- **`search`** — 3 verbs: `text`, `semantic`, `hybrid`
- **`obs`** — 3 verbs: `status`, `logs-last`, `logs-journal`

Total: 29 CLI verbs covering every server endpoint with full parameter fidelity.

Global flags:
- `--pretty` — re-encodes stdout JSON with `indent=2`. Defined on the top-level `cli` group, not per-command.

Output conventions:
- **Stdout on success:** raw server JSON, one document, no envelope, no trailing newline beyond what `click.echo` adds
- **Stdout on failure:** empty
- **Stderr on success:** empty
- **Stderr on failure:** single JSON error envelope (schema below)
- **Exit codes:** `0` success, `2` Click usage error, `4` HTTP 4xx, `5` HTTP 5xx, `1` transport error (DNS, connection refused, timeout)
- No emoji, no rich text, no progress indicators

Argument conventions:
- `path` arguments are passed positionally and forwarded verbatim to the server; path validation happens server-side
- Multi-value flags use Click's `multiple=True` (`--tag foo --tag bar`)
- Key=value flags (`--fm`) accept `KEY=VALUE` strings, split once on the first `=`. Empty value allowed. Whitespace not stripped.

### In scope

- `blackglass-client` package only — no server changes
- Every HTTP endpoint and parameter exposed as a CLI verb/flag
- Structured error handling with JSON envelope on stderr
- Output helper (`_emit`) for consistent formatting
- PATCH op body builders (`_payloads.py`)
- Full test suite using `respx` + `CliRunner`
- New `obs` command group

### Out of scope

- New server functionality (if the HTTP API can't do it, the CLI can't either)
- Client-side caching, retries, rate limiting, or response transformation
- Interactive prompts, confirmations, or progress bars
- Human-readable rendering of nested JSON beyond basic top-level key dumping
- Multi-server support (one `BLACKGLASS_URL` per invocation)

## Non-goals

1. **No new server functionality.** If the HTTP API can't do it, the CLI can't either. The CLI is a thin translation layer, not an application.
2. **No client-side caching, retries, rate limiting, or response transformation.** The CLI forwards to the server and returns what it gets.
3. **No interactive prompts, confirmations, or progress bars.** Agents need deterministic, non-interactive interfaces.
4. **No human-readable rendering of nested JSON.** Basic top-level key dumping is the ceiling. Agents parse JSON natively.
5. **No `--json` flag.** JSON is the only default output mode. The `--json` flag is removed, not renamed. Humans use `--pretty`.
6. **No backward compatibility with existing `--json` flag semantics.** We are the only consumer; no deprecation period.
7. **No new subagent groups beyond the four specified** (`notes`, `vault`, `search`, `obs`).
8. **No multi-server support.** One `BLACKGLASS_URL` per invocation via environment variable.

## Design Decisions

### 1. JSON-only output (no `--json` flag)

**Decision:** JSON is the default and only output mode. The previous `--json` flag is removed entirely.

**Trade-off:** This is backward-incompatible for any scripts relying on `--json`. However, the sole consumer is the agent, and agents always want JSON. Removing the flag simplifies every command (no conditional output formatting) and eliminates a source of bugs (forgetting to pass `--json`). The `--pretty` flag handles the human-readable case with `indent=2` re-encoding. This is a clean break — no deprecation period needed since we are the only consumer.

### 2. Centralized error handling in `client.py`

**Decision:** All HTTP and transport errors are caught in `client.py`'s `request()` function, which emits a structured JSON envelope to stderr and calls `sys.exit(N)`. Command bodies never see exceptions.

**Trade-off:** This puts error handling in one place instead of every command, which is cleaner but means command authors can't customize error behavior per-verb. Acceptable because every command needs the same error shape. The alternative — try/except in every command — would produce inconsistent error formats across 29 verbs. The envelope carries enough information for agents to diagnose any failure.

Error envelope schema:
```json
{
    "error": "http_error | transport_error",
    "status": "<int or null>",
    "method": "GET | POST | PUT | PATCH | DELETE",
    "path": "/vault/notes/foo.md",
    "detail": "<server detail or transport exception message>"
}
```

The `_extract_detail()` helper tries to parse the response body as JSON and return its `detail` field (FastAPI convention); falls back to the raw text body if not JSON. The 409 from `notes replace` (multi-match) returns a structured `detail` (`{message, match_count}`); the envelope carries that through unchanged so agents can read `match_count` from stderr.

Exit code routing:
- `400-499` → exit code `4`
- `500-599` → exit code `5`
- `httpx.RequestError` (DNS, connection refused, timeout) → exit code `1`
- Click usage errors → exit code `2` (Click default)

### 3. `_emit()` as single output helper

**Decision:** A single `_emit(data, pretty)` function in `cli/_output.py` replaces all per-file `_out()` helpers.

```python
def _emit(data: dict | list | None, pretty: bool) -> None:
    if data is None:
        return
    if pretty:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(json.dumps(data, separators=(",", ":")))
```

**Trade-off:** Slightly less flexibility (every command uses the same formatting), but eliminates the inconsistency of multiple output helpers that evolved separately. `pretty` is pulled from the Click context, set once by the global `--pretty` flag on the `cli` group. No per-command flag needed — agents never pass it, humans set it once.

### 4. `_payloads.py` for PATCH body construction

**Decision:** PATCH op builders live in `cli/_payloads.py` and are shared between `notes` and `vault periodic patch-today`.

```python
def patch_op_append(content: str) -> dict:
    return {"op": "append", "content": content}

def patch_op_prepend(content: str) -> dict: ...
def patch_op_set_frontmatter(key: str, value: str) -> dict: ...
def patch_op_replace(old: str, new: str, replace_all: bool) -> dict: ...
```

**Trade-off:** Adds a module for four small functions. But these functions appear in two command modules (`notes.py` and `vault_cmds.py`), and duplicating them would create semantic drift. The shared module keeps the op shapes identical everywhere. Both `notes replace` and `vault periodic patch-today replace` produce the same body structure.

### 5. `obs` as flat verb names (not nested subgroup)

**Decision:** `obs status`, `obs logs-last`, `obs logs-journal` use flat verb names with hyphens rather than a nested `obs logs last` / `obs logs journal` subgroup.

**Trade-off:** Flat naming is more discoverable from `--help` for agents — one listing vs. requiring `obs logs --help` to discover the subcommands. The hyphenated names (`logs-last`, `logs-journal`) are slightly unusual but unambiguous, and agents handle them fine. The alternative (a `logs` subgroup with `last`/`journal` subcommands) adds an extra `--help` hop for minimal organizational benefit.

### 6. `vault periodic list` renaming

**Decision:** What was previously `vault periodic` (no subcommand) becomes `vault periodic list` so the `periodic` noun can host subcommands (`today`, `yesterday`, `on`, `append-today`, `patch-today`).

**Trade-off:** Breaking change for any existing script calling `vault periodic` with no subcommand. Acceptable because we are the only consumer, and the flat `periodic` noun couldn't host the new subcommands. The `periodic` group now has 6 subcommands, all discoverable from `vault periodic --help`.

`vault periodic patch-today` is a nested group with four subcommands:
- `vault periodic patch-today append <content>`
- `vault periodic patch-today prepend <content>`
- `vault periodic patch-today set-frontmatter <key> <value>`
- `vault periodic patch-today replace --old <s> --new <s> [--replace-all]`

These POST to the same endpoint as the corresponding `notes` PATCH ops, using the shared `_payloads.py` builders.

### 7. Exit code matrix (not per-verb codes)

**Decision:** Five exit codes: 0 (success), 1 (transport), 2 (usage), 4 (HTTP 4xx), 5 (HTTP 5xx). Same codes for every verb.

**Trade-off:** Agents can't distinguish a 404 from a 409 by exit code alone — they must parse the stderr envelope's `status` field. But a fine-grained exit code scheme would explode the matrix (29 verbs × N error codes) and make shell scripting harder (`if [ $? -eq 4 ]` is simpler than remembering 40+ codes). The envelope carries the detail; the exit code carries the category. This is the right split for programmatic consumption.

### 8. `--content` as string flag, not file path

**Decision:** `--content` for `create`/`update` accepts literal string content. For very long content, users pipe via shell (`--content "$(cat foo.md)"`).

**Trade-off:** No `--file` flag for reading from a file path. This keeps the interface simple and avoids an extra flag that would need its own error handling (file not found, permission denied). Shell substitution covers the file case, and agents typically generate content programmatically anyway. A deferred open question is whether `--content -` should mean "read from stdin" (common Unix convention), but agents can use shell substitution for now.

### 9. `notes batch` with `--stdin` mutual exclusion

**Decision:** `notes batch` accepts paths as positional varargs OR via `--stdin` (newline-separated), but not both. Passing both is a usage error (exit 2). Max 50 paths (server-enforced); the CLI does not pre-validate.

**Trade-off:** `--stdin` and positional paths being mutually exclusive adds a small validation step. But allowing both would require a merge strategy (prepend? append? deduplicate?) that isn't worth the complexity. The 50-path limit is enforced server-side, so the CLI just forwards and lets the 400 propagate if exceeded.

### 10. `notes move` with `--no-rewrite-links`

**Decision:** `notes move <src> <dst>` has a `--no-rewrite-links` flag that sets `rewrite_links: false` in the body. Server default is true; omitting the flag preserves the default.

**Trade-off:** A negation flag (`--no-rewrite-links`) rather than a positive flag (`--rewrite-links`). This matches the common case — link rewriting is almost always desired, so the flag exists to opt out. The server default of `true` means the CLI body omits the field entirely when the flag is not passed, letting the server apply its default.

## Changes

### New files

| File | Purpose |
|------|---------|
| `cli/_output.py` | `_emit(data, pretty)` helper — single output path for all commands |
| `cli/_payloads.py` | PATCH op builders: `patch_op_append`, `patch_op_prepend`, `patch_op_set_frontmatter`, `patch_op_replace` |
| `cli/obs_cmds.py` | `obs` command group: `status`, `logs-last`, `logs-journal` |
| `tests/conftest.py` | Click `CliRunner` fixture + `respx` mock fixture |
| `tests/test_notes.py` | Happy-path tests for all 11 `notes` verbs |
| `tests/test_vault.py` | Happy-path tests for `vault` verbs |
| `tests/test_periodic.py` | Happy-path tests for `vault periodic` subgroup |
| `tests/test_search.py` | Happy-path tests for all 3 `search` verbs |
| `tests/test_obs.py` | Happy-path tests for all 3 `obs` verbs |
| `tests/test_errors.py` | Error envelope + exit code matrix (5 tests covering 400, 404, 409, 500, transport) |

### Modified files

| File | Changes |
|------|---------|
| `client.py` | Added error envelope + `sys.exit()` logic. Catches `httpx.HTTPStatusError` (→ exit 4/5) and `httpx.RequestError` (→ exit 1). `_extract_detail()` parses FastAPI `detail` field. |
| `cli/main.py` | Added `--pretty` global flag on `cli` group. Registered `obs` subgroup. |
| `cli/notes.py` | Dropped `--json`. Added `meta`, `prepend`, `replace`, `batch`, `move`. Uses `_emit()` and `_payloads.py`. |
| `cli/vault_cmds.py` | Dropped `--json`. Renamed `periodic` → `periodic list`. Added `periodic today|yesterday|on|append-today|patch-today`. Added `changes`. Expanded `files` flags. |
| `cli/search_cmds.py` | Dropped `--json`. Added `hybrid`. Added `--snippet-chars` to all three. |
| `pyproject.toml` | Added `dev` extras: `pytest`, `respx`. |

### Deleted patterns

- Per-file `_out()` helpers → replaced by `_emit()` from `_output.py`
- `--json` flag → removed from all commands
- `notes delete` output `Deleted: <path>` → removed; exit code 0 is the success signal
- No deprecation period for any of these (we are the only consumer)

### Command map (complete)

**`notes` group (11 verbs):**

| CLI verb | HTTP | Path | Flags / args |
|----------|------|------|-------------|
| `notes get <path>` | GET | `/vault/notes/{path}` | — |
| `notes meta <path>` | GET | `/vault/notes/{path}/meta` | — |
| `notes create <path> --content <s>` | POST | `/vault/notes?path=...` | `--content` (required) |
| `notes update <path> --content <s>` | PUT | `/vault/notes/{path}` | `--content` (required) |
| `notes append <path> <content>` | PATCH | `/vault/notes/{path}` | body: `{op: "append", content}` |
| `notes prepend <path> <content>` | PATCH | `/vault/notes/{path}` | body: `{op: "prepend", content}` |
| `notes set-frontmatter <path> <key> <value>` | PATCH | `/vault/notes/{path}` | body: `{op: "set_frontmatter", key, value}` |
| `notes replace <path> --old <s> --new <s> [--replace-all]` | PATCH | `/vault/notes/{path}` | body: `{op: "replace", old, new, replace_all}` |
| `notes delete <path>` | DELETE | `/vault/notes/{path}` | — |
| `notes batch <paths...>` | POST | `/vault/notes/batch` | positional varargs; `--stdin` (mutually exclusive) |
| `notes move <src> <dst> [--no-rewrite-links]` | POST | `/vault/notes/{src}/move` | body: `{to: dst, rewrite_links: bool}` |

**`vault` group (12 verbs):**

| CLI verb | HTTP | Path | Flags |
|----------|------|------|-------|
| `vault files` | GET | `/vault/files` | `--tag` (×N), `--fm K=V` (×N), `--path-glob`, `--limit` |
| `vault tags` | GET | `/vault/tags` | — |
| `vault backlinks <path>` | GET | `/vault/backlinks/{path}` | — |
| `vault sync` | POST | `/vault/sync` | — |
| `vault changes` | GET | `/vault/changes` | `--since`, `--days`, `--limit`, `--diff-stats` |
| `vault periodic list` | GET | `/vault/periodic` | — |
| `vault periodic today` | GET | `/vault/periodic/today` | — |
| `vault periodic yesterday` | GET | `/vault/periodic/yesterday` | — |
| `vault periodic on <YYYY-MM-DD>` | GET | `/vault/periodic/by-date/{date}` | — |
| `vault periodic append-today <content>` | POST | `/vault/periodic/today/append` | body: `{content}` |
| `vault periodic patch-today <op> [args]` | PATCH | `/vault/periodic/today` | 4 sub-ops mirroring `notes` PATCH |

**`search` group (3 verbs):**

| CLI verb | HTTP | Path | Flags |
|----------|------|------|-------|
| `search text <query>` | GET | `/vault/search` | `--snippet-chars` (default 300, server-clamped) |
| `search semantic <query>` | GET | `/vault/semantic-search` | `--limit`, `--snippet-chars` |
| `search hybrid <query>` | GET | `/vault/hybrid-search` | `--limit`, `--snippet-chars`, `--k` |

All three accept `--snippet-chars 0` to suppress snippet generation. `hybrid` returns `{results, degraded}` shape; the CLI does not flatten it.

**`obs` group (3 verbs, new):**

| CLI verb | HTTP | Path | Flags |
|----------|------|------|-------|
| `obs status` | GET | `/status` | — |
| `obs logs-last` | GET | `/logs/last` | `-n` (1..200, default 50) |
| `obs logs-journal` | GET | `/logs/journal` | `-n` (1..2000, default 100) |

## Acceptance Criteria

### Command surface

1. Every row in the command map (29 verbs) corresponds to a working CLI verb.
2. `blackglass --help` lists `notes`, `vault`, `search`, `obs` as subgroups.
3. `blackglass notes --help` lists all 11 verbs.
4. `blackglass vault --help` lists all verbs including `periodic` subgroup.
5. `blackglass search --help` lists `text`, `semantic`, `hybrid`.
6. `blackglass obs --help` lists `status`, `logs-last`, `logs-journal`.

### Happy-path tests

7. For every verb (29 total), a mocked-server test passes with exit code 0 and stdout equal to the server response.
8. `--pretty` produces indented JSON with `indent=2` on stdout.
9. Multi-value flags (`--tag foo --tag bar --fm a=1 --fm b=2`) produce the expected repeated query string.
10. `notes batch a.md b.md` sends `{"paths": ["a.md", "b.md"]}` to the server.
11. `notes batch --stdin` reads newline-separated paths from stdin correctly.
12. `notes batch` with both positional and `--stdin` is a usage error (exit 2).
13. `vault periodic patch-today append <content>` sends correct PATCH body.
14. `vault periodic patch-today replace --old X --new Y --replace-all` sends correct body.
15. `vault changes --since 2026-01-01 --limit 10 --diff-stats` sends all query params.

### Error handling

16. HTTP 400 → stderr envelope with `error: "http_error"`, `status: 400`, exit code 4.
17. HTTP 404 → stderr envelope with `status: 404`, exit code 4.
18. HTTP 409 (from `notes replace` multi-match) → stderr envelope with `detail` containing `match_count`, exit code 4.
19. HTTP 500 → stderr envelope with `status: 500`, exit code 5.
20. Transport error (connection refused) → stderr envelope with `error: "transport_error"`, `status: null`, exit code 1.
21. Stdout is empty on all error paths.
22. Stderr is empty on all success paths.

### Negative checks

23. No `--json` flag survives anywhere in the CLI surface (`--help` output for all groups).
24. `notes delete` on success produces no stdout output (exit code 0 is the signal).
25. `vault periodic` with no subcommand is an error (not a passthrough to list).

### Test coverage

26. ~30 happy-path tests (one per CLI verb) all pass.
27. 5 error matrix tests (400, 404, 409, 500, transport) all pass.
28. No tests run against a live server; all use `respx` mocks.
