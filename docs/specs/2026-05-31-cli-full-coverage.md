# Blackglass CLI Full Coverage: Design Spec

**Status:** draft, v1
**Audience:** Claude Code / openclaw and similar agents using the blackglass CLI
**Scope:** the `blackglass-client` package only. No server changes.

## Goal

Bring `blackglass-client` to 100% endpoint and parameter fidelity with the server. Every server route reachable via a CLI verb; every query param and body field that affects output reachable via a CLI flag. The CLI is the primary agentic interface to blackglass; agents must be able to do anything the HTTP API offers without falling back to raw `curl`.

## Non-goals

- No new server functionality. If the HTTP API can't do it, the CLI can't either.
- No client-side caching, retries, rate limiting, or response transformation.
- No interactive prompts, confirmations, or progress bars.
- No human-readable rendering of nested JSON beyond basic top-level key dumping.
- No `--json` flag. JSON is the only default output mode.
- No backward compatibility with the existing `--json` flag semantics (it gets removed, not renamed).
- No new subagent groups beyond what the design specifies.
- No multi-server support; one `BLACKGLASS_URL` per invocation.

## Conventions

- Stdout on success: raw server JSON, one document, no envelope, no trailing newline beyond what `click.echo` adds.
- Stdout on failure: empty.
- Stderr on success: empty.
- Stderr on failure: a single JSON object describing the error (schema below).
- Exit codes: `0` on success, `4` on HTTP 4xx, `5` on HTTP 5xx, `2` on Click usage errors (default Click behavior), `1` on any other transport error (DNS, connection refused, timeout).
- `--pretty` is a global flag (defined on `cli`) that re-encodes stdout JSON with `indent=2`. It does not change semantics.
- No emoji, no rich text, no progress indicators.
- `path` arguments are passed positionally and forwarded verbatim to the server. Path validation happens server-side.
- Multi-value flags use Click's `multiple=True` (`--tag foo --tag bar`).
- Key=value flags (`--fm`) accept `KEY=VALUE` strings, split once on the first `=`. Empty value allowed. Whitespace not stripped.

## Architecture

### Client transport layer (`client.py`)

`client.py` stays minimal but gains error-routing logic. The current `request()` raises `httpx.HTTPStatusError` on non-2xx; that bubbles up as a Python traceback, which is hostile to agentic consumption.

New behavior: `request()` catches `httpx.HTTPStatusError` and `httpx.RequestError`, emits a structured JSON envelope to stderr, and calls `sys.exit(N)` with the appropriate exit code. The CLI command body never sees an exception path. This puts error handling in one place instead of every command.

```python
# Error envelope written to stderr on failure
{
    "error": "http_error" | "transport_error",
    "status": <int or null>,       # HTTP status if available
    "method": "GET" | "POST" | ...,
    "path": "/vault/notes/foo.md",
    "detail": <server detail or transport exception message>
}
```

The function signature stays `request(method, path, **kwargs) -> dict | list | None` for the success path.

### CLI module layout

Existing modules expand; one new module added:

```
blackglass_client/cli/
  __init__.py
  main.py            # top-level group; --pretty global; registers subgroups
  notes.py           # notes verbs (CRUD + PATCH ops + meta + batch + move)
  vault_cmds.py      # vault verbs (files/tags/backlinks/sync/changes + periodic subgroup)
  search_cmds.py     # search verbs (text/semantic/hybrid)
  obs_cmds.py        # NEW: observability verbs (status, logs)
```

`vault_cmds.py` gains a nested `periodic` subgroup. `notes.py` gains `move`. `obs_cmds.py` is a new file with a top-level `obs` group registered in `main.py`.

No splitting `notes.py` into per-verb modules. The file stays under 200 lines even after the expansion, and keeping it co-located mirrors the server's `notes.py` boundary.

### Output helper

A single `_emit(data, pretty)` function lives in a new `cli/_output.py` and is imported by every command module. The current per-file `_out()` helpers are deleted.

```python
def _emit(data: dict | list | None, pretty: bool) -> None:
    if data is None:
        return
    if pretty:
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(json.dumps(data, separators=(",", ":")))
```

`pretty` is pulled from the Click context, set by the top-level `--pretty` flag on `cli`. No per-command flag needed; agents never pass it, humans set it once at the group level.

## Command map

Format: `<cli verb>  ->  <HTTP method> <path>  (flags)`

### `notes`

| CLI verb | HTTP | Path | Flags / args |
|---|---|---|---|
| `notes get <path>` | GET | `/vault/notes/{path}` | - |
| `notes meta <path>` | GET | `/vault/notes/{path}/meta` | - |
| `notes create <path> --content <s>` | POST | `/vault/notes?path=...` | `--content` (required) |
| `notes update <path> --content <s>` | PUT | `/vault/notes/{path}` | `--content` (required) |
| `notes append <path> <content>` | PATCH | `/vault/notes/{path}` | body: `{op: append, content}` |
| `notes prepend <path> <content>` | PATCH | `/vault/notes/{path}` | body: `{op: prepend, content}` |
| `notes set-frontmatter <path> <key> <value>` | PATCH | `/vault/notes/{path}` | body: `{op: set_frontmatter, key, value}` |
| `notes replace <path> --old <s> --new <s> [--replace-all]` | PATCH | `/vault/notes/{path}` | body: `{op: replace, old, new, replace_all}` |
| `notes delete <path>` | DELETE | `/vault/notes/{path}` | - |
| `notes batch <paths...>` | POST | `/vault/notes/batch` | positional varargs; `--stdin` reads newline-separated paths from stdin instead |
| `notes move <src> <dst> [--no-rewrite-links]` | POST | `/vault/notes/{src}/move` | body: `{to: dst, rewrite_links: bool}` (default true server-side; flag negates) |

Notes:
- `--content` for `create` / `update` is a string flag, not a file path. Agents pass the literal content. For very long content, pipe via shell (the user can use `--content "$(cat foo.md)"`).
- `notes replace`: `--replace-all` is a flag; server defaults to false. On `409` with `match_count`, the error envelope passes the server's structured detail through unchanged.
- `notes batch`: max 50 paths (server-enforced). The CLI does not pre-validate; let the 400 propagate. `--stdin` and positional paths are mutually exclusive; passing both is a usage error (exit 2).
- `notes move`: `--no-rewrite-links` sets `rewrite_links: false` in the body. Server default is true, so omitting the flag preserves server default.

### `vault`

| CLI verb | HTTP | Path | Flags |
|---|---|---|---|
| `vault files [--tag T]... [--fm K=V]... [--path-glob G] [--limit N]` | GET | `/vault/files` | repeated `--tag`, repeated `--fm key=value`, `--path-glob`, `--limit` |
| `vault tags` | GET | `/vault/tags` | - |
| `vault backlinks <path>` | GET | `/vault/backlinks/{path}` | - |
| `vault sync` | POST | `/vault/sync` | - |
| `vault changes [--since S | --days N] [--limit N] [--diff-stats]` | GET | `/vault/changes` | `--since`, `--days`, `--limit`, `--diff-stats` |
| `vault periodic list` | GET | `/vault/periodic` | - |
| `vault periodic today` | GET | `/vault/periodic/today` | - |
| `vault periodic yesterday` | GET | `/vault/periodic/yesterday` | - |
| `vault periodic on <YYYY-MM-DD>` | GET | `/vault/periodic/by-date/{date}` | - |
| `vault periodic append-today <content>` | POST | `/vault/periodic/today/append` | body: `{content}` |
| `vault periodic patch-today <op> [<arg>...]` | PATCH | `/vault/periodic/today` | mirrors `notes` PATCH op subcommands |

Notes:
- `vault files` flags map 1:1 to server query params. `--fm` is parsed with one `split("=", 1)` per occurrence; multiple `--fm` flags build a dict. Duplicate keys are rejected server-side with 400; CLI does not pre-check.
- `vault periodic list` renames what used to be plain `vault periodic` so the noun can host subcommands. Breaking change for any existing script calling `vault periodic` with no subcommand. Acceptable; we are the only consumer.
- `vault periodic patch-today` takes an op name as positional and dispatches like the corresponding `notes` PATCH:
  - `vault periodic patch-today append <content>`
  - `vault periodic patch-today prepend <content>`
  - `vault periodic patch-today set-frontmatter <key> <value>`
  - `vault periodic patch-today replace --old <s> --new <s> [--replace-all]`

  Implementation: a nested `periodic_patch_today` group with four subcommands that POST to the same endpoint.

### `search`

| CLI verb | HTTP | Path | Flags |
|---|---|---|---|
| `search text <query> [--snippet-chars N]` | GET | `/vault/search` | `--snippet-chars` (default 300, server-clamped) |
| `search semantic <query> [--limit N] [--snippet-chars N]` | GET | `/vault/semantic-search` | `--limit`, `--snippet-chars` |
| `search hybrid <query> [--limit N] [--snippet-chars N] [--k N]` | GET | `/vault/hybrid-search` | `--limit`, `--snippet-chars`, `--k` |

Notes:
- All three accept `--snippet-chars 0` to suppress snippet generation.
- `hybrid` returns `{results, degraded}` shape; the CLI does not flatten it.

### `obs` (new group)

| CLI verb | HTTP | Path | Flags |
|---|---|---|---|
| `obs status` | GET | `/status` | - |
| `obs logs-last [-n N]` | GET | `/logs/last` | `-n` (1..200, default 50) |
| `obs logs-journal [-n N]` | GET | `/logs/journal` | `-n` (1..2000, default 100) |

Notes:
- Two separate verbs (`logs-last`, `logs-journal`) rather than a `logs` subgroup. Flat naming is more discoverable from `--help` for agents.

## Body construction patterns

To prevent ad-hoc body building in every command, three helpers live in `cli/_payloads.py`:

```python
def patch_op_append(content: str) -> dict:
    return {"op": "append", "content": content}

def patch_op_prepend(content: str) -> dict: ...
def patch_op_set_frontmatter(key: str, value: str) -> dict: ...
def patch_op_replace(old: str, new: str, replace_all: bool) -> dict: ...
```

`notes` and `vault periodic patch-today` both import these. Eliminates the four-op switch from appearing in two places.

## Error semantics

Implemented in `client.py`. Pseudocode:

```python
def request(method, path, **kwargs):
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

`_extract_detail()` tries to parse the response body as JSON and return its `detail` field (FastAPI convention); falls back to the raw text body if not JSON.

The 409 from `notes replace` (multi-match) returns a structured `detail` (`{message, match_count}`); the envelope's `detail` field carries that through unchanged so agents can read `match_count` from stderr.

## Backward-incompatible changes

1. `--json` flag removed from every command. JSON is default; humans use `--pretty`.
2. `vault periodic` (no subcommand) now errors; use `vault periodic list`.
3. `_out()` per-file helpers deleted; `_emit()` from `cli/_output.py` replaces them.
4. The current `notes delete` prints `Deleted: <path>` on success. After the change it prints nothing (matches the 204 + no-envelope rule). Exit code 0 is the success signal.

No deprecation period. We are the only consumer.

## Testing

The client has no test suite today. This spec adds one, scoped to the CLI layer only (the server has its own tests).

### Layout

```
blackglass-client/tests/
  conftest.py          # Click CliRunner fixture + respx mock fixture
  test_notes.py
  test_vault.py
  test_periodic.py
  test_search.py
  test_obs.py
  test_errors.py       # error envelope + exit code matrix
```

### Approach

Use `respx` to mock httpx calls; use Click's `CliRunner` to invoke commands. Each test asserts:

1. Correct HTTP method, path, and body sent to the server.
2. Stdout matches the mocked server response verbatim (modulo `--pretty` formatting).
3. Exit code is 0 on success, 4/5 on error.
4. Stderr is empty on success, contains valid JSON envelope on error.

### Required coverage

One happy-path test per CLI verb (about 30 tests). The error matrix file covers one 400, one 404, one 409, one 500, and one transport error: five tests total, since the envelope shape is shared across all verbs and there is no need to repeat per-verb.

Multi-value flag tests: one test that `--tag foo --tag bar --fm a=1 --fm b=2` produces the expected repeated query string. One test that `notes batch a.md b.md` sends `{"paths": ["a.md", "b.md"]}`. One test that `notes batch --stdin` reads from stdin correctly.

No tests against a live server. No tests for `client.py` internals beyond what the CLI tests exercise transitively.

### Tooling

`pytest`, `respx`, `click.testing.CliRunner`. Add to `blackglass-client/pyproject.toml` as `[project.optional-dependencies] dev = [...]`.

## Open questions

1. Should `--content` accept `-` to mean "read from stdin"? Common Unix convention. Adds complexity. Defer to a follow-up; agents can use shell substitution for now.
2. Should `notes batch` accept JSON on stdin (instead of paths-only) for forward compatibility if batch later grows? No: keep it simple. The endpoint is paths-only today and any expansion warrants a new verb.
3. Global `--api-key` and `--url` flags on `cli`? Currently only env vars. Defer; env vars are sufficient for the agentic case and adding flags expands the test matrix.

## Acceptance criteria

1. Every row in the command map above corresponds to a working CLI verb.
2. `blackglass --help` lists `notes`, `vault`, `search`, `obs`.
3. For every verb, mocked-server tests pass with exit code 0 and stdout equal to the server response.
4. For every HTTP error class (4xx, 5xx) and for transport errors, the stderr envelope contains the documented fields and the exit code matches the matrix.
5. No `--json` flag survives anywhere in the CLI surface.
6. Running `blackglass --pretty notes get foo.md` against a real server returns indented JSON on stdout.

## File-by-file change list

- `blackglass-client/src/blackglass_client/client.py`: add error envelope + sys.exit logic.
- `blackglass-client/src/blackglass_client/cli/main.py`: add `--pretty` global flag, register `obs` group.
- `blackglass-client/src/blackglass_client/cli/_output.py`: NEW, `_emit()` helper.
- `blackglass-client/src/blackglass_client/cli/_payloads.py`: NEW, PATCH op builders.
- `blackglass-client/src/blackglass_client/cli/notes.py`: drop `--json`; add `meta`, `prepend`, `replace`, `batch`, `move`.
- `blackglass-client/src/blackglass_client/cli/vault_cmds.py`: drop `--json`; rename `periodic` to `periodic list`; add `periodic today|yesterday|on|append-today|patch-today`; add `changes`; expand `files` flags.
- `blackglass-client/src/blackglass_client/cli/search_cmds.py`: drop `--json`; add `hybrid`; add `--snippet-chars` to all three.
- `blackglass-client/src/blackglass_client/cli/obs_cmds.py`: NEW, `status` / `logs-last` / `logs-journal`.
- `blackglass-client/pyproject.toml`: add `dev` extras for pytest + respx.
- `blackglass-client/tests/`: NEW directory per the testing section.
