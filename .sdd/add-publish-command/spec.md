# Spec: add-publish-command

## Goal

Add a `blackglass publish` top-level CLI command that fetches a note from the Blackglass vault, strips its YAML frontmatter, and publishes the content as a public GitHub Gist under the user's account. This gives users a one-command way to share vault notes externally.

## Interface / Scope

### What the user sees

```
blackglass publish "Flanagan vs. Craig.md"
```

Output (JSON on stdout, like all other commands):
```json
{
  "url": "https://gist.github.com/acesanderson/e0a3d8bfa647239c78485664215ae0de",
  "id": "e0a3d8bfa647239c78485664215ae0de",
  "filename": "Flanagan vs. Craig.md",
  "public": true
}
```

Flags:
- `--private` — publish as a private gist instead of public (default: public)

Authentication:
- Requires `GITHUB_PERSONAL_TOKEN` env var (fine-grained or classic PAT with `gist` scope)
- If unset: exit with code 1 and clear error message on stderr

Gist metadata:
- **Description**: `"{title} — published from Blackglass {date}"` where:
  - `title` = note filename without `.md` extension
  - `date` = frontmatter `date` field if present, otherwise today's date (YYYY-MM-DD)
- **Filename**: the note's original filename (e.g., `Flanagan vs. Craig.md`)

### What's in scope

- Fetching a note via the blackglass HTTP API (`GET /vault/notes/{path}`)
- Stripping YAML frontmatter (content between first `---` delimiters)
- Creating a gist via GitHub REST API (`POST /gists`)
- Public and private gist creation
- Error handling for missing token, missing note, GitHub API failures

### What's explicitly out of scope

- Updating or deleting existing gists
- Publishing multiple notes in one command
- Custom gist description (always auto-generated)
- Markdown-to-HTML rendering (gists render markdown natively)
- Markdown-to-PDF or other export formats
- Listing or managing existing gists
- Caching or syncing gist state back to vault

## Non-goals

1. **Gist management** — this is publish-only. No update, delete, list, or fork.
2. **Batch publishing** — one note per command invocation. Script it if you need bulk.
3. **Custom descriptions** — the description is deterministic and auto-generated.
4. **Server-side changes** — this is a client-only feature. No new server endpoints.
5. **Authentication management** — we don't store or manage the GitHub token. Env var only.

## Design decisions

1. **Top-level command (`blackglass publish`) vs. subcommand (`blackglass notes publish`)**
   - Chosen: top-level. Publishing is a distinct action, not a note CRUD operation.
   - Rejected: `notes publish` — conflates reading/editing notes with external publishing.

2. **GitHub API via httpx (already a dependency) vs. subprocess `gh` CLI**
   - Chosen: httpx. Zero additional dependencies, deterministic, testable with respx.
   - Rejected: `gh` CLI — requires installation, auth flow is interactive, output parsing is fragile.

3. **Frontmatter stripping in Python vs. regex in shell**
   - Chosen: Python. Reliable YAML-aware parsing handles edge cases (content with `---` lines).
   - Rejected: regex — brittle, would break on horizontal rules in note content.

4. **Env var (`GITHUB_PERSONAL_TOKEN`) vs. `gh auth` token**
   - Chosen: env var. Consistent with existing blackglass pattern (uses `BLACKGLASS_API_KEY` env var).
   - Rejected: `gh auth` — adds dependency on `gh` CLI, harder to test.

5. **Public by default vs. private by default**
   - Chosen: public. The command is called "publish" — intent is external sharing.
   - Flag: `--private` for when needed.

## Changes

### Create: `src/blackglass_client/cli/publish.py`

New Click command module. Functions:
- `strip_frontmatter(content: str) -> str` — strips YAML frontmatter between first `---` delimiters
- `get_note_date(content: str) -> str` — extracts `date` from frontmatter, falls back to today
- `publish_note(path: str, private: bool) -> dict` — orchestrates: fetch note → strip frontmatter → create gist → return result
- `publish` Click command — CLI entry point

Key implementation notes:
- Uses `httpx` for both blackglass API and GitHub API calls
- Reads `GITHUB_PERSONAL_TOKEN` from env via `os.environ`
- Blackglass API base URL from env or default `http://localhost:8083`
- GitHub API: `POST https://api.github.com/gists` with `Authorization: token {token}`
- Frontmatter strip: split on `\n---\n`, take everything after second occurrence
- Date extraction: regex on frontmatter for `date: YYYY-MM-DD`
- Error cases: missing token (exit 1), note not found (propagate 404), GitHub error (exit 1 with message)

### Modify: `src/blackglass_client/cli/main.py`

Add import and register the new command:
```python
from .publish import publish
cli.add_command(publish)
```

### Create: `tests/test_publish.py`

Tests using pytest + respx (already in dev deps):
- `test_strip_frontmatter` — strips correctly, handles no frontmatter, handles `---` in content
- `test_get_note_date` — extracts date from frontmatter, falls back to today
- `test_publish_happy_path` — mocks both APIs, verifies correct requests and output
- `test_publish_missing_token` — env var unset, exits 1
- `test_publish_note_not_found` — server returns 404, propagates error
- `test_publish_github_error` — GitHub API returns 4xx, exits 1 with message
- `test_publish_private` — `--private` flag creates private gist

## Acceptance criteria

1. `blackglass publish "Note.md"` creates a public gist and prints the JSON URL
2. `blackglass publish "Note.md" --private` creates a private gist
3. The gist description is `"{title} — published from Blackglass {date}"` using frontmatter date or today
4. YAML frontmatter is stripped from the gist content
5. The gist filename matches the original note filename
6. If `GITHUB_PERSONAL_TOKEN` is unset, the command exits with code 1 and a clear error
7. If the note doesn't exist in the vault, the command exits with code 4
8. If the GitHub API returns an error, the command exits with code 1 with the error message
9. All tests pass: `uv run pytest tests/test_publish.py -v`
10. The command appears in `blackglass --help` output
