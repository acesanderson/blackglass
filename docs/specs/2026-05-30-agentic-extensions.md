# Blackglass Agentic Extensions — Design Spec

**Status:** draft, v3 (post-review, anchored-replace pivot)
**Audience:** Claude Code / openclaw and similar agents using blackglass over HTTP
**Reviewers should focus on:** the open questions section, the cross-cutting concerns, and any acceptance criterion that isn't concretely testable.

## Goal

Close the worst friction points an LLM agent hits when reading and writing the vault through blackglass: too many round-trips, too many tokens per round-trip, no way to ask "what changed," weak PATCH ops, no atomic rename, and no merged ranking across text + semantic search.

## Non-goals (explicit)

A subagent reading this MUST NOT add these without a separate spec:

- Chunked embeddings or per-section vectors. Current `_MAX_EMBED_CHARS = 2000` truncation stays. Long-doc recall loss is accepted.
- Concurrency control / multi-writer locking. Single-user vault assumption.
- Templates engine for daily notes. Auto-create produces an empty file (0 bytes).
- Undo, soft-delete, trash bin. Recovery is via `git checkout`; agents must be told this and not invent their own.
- Server-side markdown structure parsing for edits. PATCH edits use anchored find-and-replace (the LLM is a better markdown parser than any line-counting code we'd ship). No `replace_section`, no `insert_under_heading`, no code-fence awareness — by deliberate design, not omission.
- Tag-prefix or hierarchy matching (`tag=foo/*`). Exact tag match only.
- Transactional/atomic move. Move is a multi-step operation with partial-failure reporting; rollback is the caller's job.
- Multi-vault. Single `BLACKGLASS_VAULT_PATH`.
- Schema migration of existing embeddings. Sync re-indexes on hash mismatch only.
- Rate limiting / quota. Single tenant.
- Backwards-compatibility shims. Additive routes only; existing routes gain optional fields.

## Conventions

- All new routes sit behind the existing `X-API-Key` dep (`require_api_key`).
- All `path` parameters are vault-relative POSIX paths, validated with `_resolve` against vault escape. Escape attempts → 400, never 500.
- All timestamp fields are unix epoch seconds (float). `since=` query params accept ISO 8601 (with or without `Z`) OR a bare float/int (epoch seconds). Relative formats like `7d`, `yesterday` are NOT accepted; callers compute them.
- JSON keys use snake_case.
- No emoji, no rich text, no markdown in JSON values.
- `\n` line endings on write. Mixed `\r\n` on read is tolerated by line splitting but normalized on rewrite.
- String comparisons in filters / heading matches are case-sensitive and byte-exact unless stated otherwise.

## Cross-cutting concerns

### Versioning

Additive only. Two existing routes change response shape by gaining optional fields:
- `GET /vault/search` and `GET /vault/semantic-search` gain `snippet` (default present).
- `GET /vault/files` gains `total` and `filtered_from` only when a filter param is supplied; bare `GET /vault/files` returns the existing shape unchanged.

Clients that strict-validate response schemas should adopt unknown-field tolerance. This is documented as a soft break.

### Idempotency

| Route | Idempotent? |
|---|---|
| `GET /*` | yes |
| `POST /vault/notes/batch` (read) | yes |
| `POST /vault/notes/{p}/move` | NO — second call returns 404 (source gone) |
| `PATCH /vault/notes/{p}` op=append | NO — concatenates each call |
| `PATCH` op=replace (replace_all=false) | YES (404 on second call after success) |
| `PATCH` op=replace (replace_all=true) | YES (no-op on second call) |
| `PATCH` op=set_frontmatter | YES |
| `POST /vault/periodic/today/append` | NO |
| `PATCH /vault/periodic/today` | depends on op (same table) |

### Performance budgets (p99, single-user load)

| Route | Target | Hard timeout |
|---|---|---|
| `GET /status` | 100 ms | 5 s |
| `GET /logs/last` | 50 ms | 2 s |
| `GET /logs/journal` | 500 ms | 10 s |
| `GET /vault/semantic-search` (with snippet) | 500 ms | 30 s |
| `GET /vault/search` (with snippet) | 1 s | 30 s |
| `POST /vault/notes/batch` (50 paths) | 1 s | 30 s |
| `GET /vault/changes` (days≤30) | 1 s | 10 s |
| `GET /vault/files` (any filter) | 2 s | 30 s |
| `GET /vault/notes/{p}/meta` | 50 ms | 5 s |
| `POST /vault/notes/{p}/move` (rewrite_links=true) | 3 s | 60 s |
| `GET /vault/hybrid-search` | 1 s | 30 s |
| `PATCH /vault/notes/{p}` (any op) | 500 ms | 30 s |

Routes that exceed their hard timeout return 504. Subprocess calls (git, journalctl) MUST be invoked with `timeout=` matching the hard limit.

### Payload caps

- PATCH `content` field: 1 MiB max. Over → 413.
- Batch read input: 50 paths max. Over → 400.
- Snippet length: 1000 chars max. Over → 400.
- Move `to` path: existing `_resolve` rules apply.

### Security

- Path traversal: `_resolve` is the single chokepoint. Every new route MUST call it (or `list_files`) for path inputs. No new code may `open(vault_path / x)` without `_resolve` first.
- Move `to` is `_resolve`d. A `to` outside the vault → 400.
- PATCH/POST content is written verbatim. No HTML/JS sanitization. Markdown is plain text.
- Auth on `/logs/journal` is non-negotiable — journal output leaks request paths and bodies.

### Observability requirements (the bar to be "done in prod")

Every new endpoint MUST emit a single structured INFO log line on success and WARN/ERROR on failure. Required fields:

```
{
  "route": "<route name, e.g. /vault/notes/batch>",
  "request_id": "<correlation ID from middleware>",
  "result_kind": "ok | not_found | error | partial",
  "result_count": <int, where meaningful — list length, files rewritten, etc.>,
  "duration_ms": <float>
}
```

Per-feature `extra` fields are listed in each feature's Observability section.

Each feature's acceptance criteria includes a "verifiable from logs alone" line: a human reading 24h of journal should be able to confirm the endpoint is functioning.

`/status` is extended with `recent_op_counts`: a rolling 1-hour counter per route, derived from the ring buffer. Implementation: scan ring buffer, count `result_kind` per `route`. Cheap, no separate metrics store.

### Error response shape

All errors use FastAPI's default `{"detail": "<string>"}` unless an endpoint specifies otherwise (e.g., batch read returns 200 with per-item status). 4xx is client error, 5xx is server error, 504 is timeout.

---

## 1. Snippets in semantic-search and search

### Goal
Return a server-rendered text excerpt with each search hit so agents don't pay N round-trips to judge relevance.

### Route (changes existing)
```
GET /vault/semantic-search?q=<query>&limit=<int>&snippet_chars=<int>
GET /vault/search?q=<query>&snippet_chars=<int>
```

Defaults: `limit=10`, `snippet_chars=300`. `snippet_chars=0` returns no `snippet` field (bandwidth opt-out).

### Response
```json
[
  {
    "path": "Middlegame NOC.md",
    "score": 0.697,
    "snippet": "Hosts: caruana (LAN host), alphablue (GPU worker), botvinnik (embeddings)..."
  }
]
```

### Semantics
- `snippet` is computed as: read file → `split_frontmatter` (existing util) → take `body` → `strip()` leading whitespace → `body[:snippet_chars + 100]` (read 100 extra to find word boundary) → if the last char inside the limit is not whitespace AND a whitespace char exists within 50 chars before the limit, truncate at that whitespace; else hard-truncate at `snippet_chars`.
- "Whitespace" means ASCII space/tab/newline only. Multi-byte awareness is out of scope.
- If `body` is shorter than `snippet_chars`, `snippet` equals `body` exactly (no padding).
- Frontmatter without closing `---` (malformed) → `split_frontmatter` returns `({}, full_text)`; snippet is from full text. Documented.
- File missing/unreadable when snippet is being computed → `snippet: ""`. Hit is still returned (DB row is the source of truth for relevance).

### Failure modes
| Condition | Behavior |
|---|---|
| `q` empty | 400 `{"detail": "q is required"}` |
| `limit > 100` | 400 |
| `snippet_chars > 1000` | 400 |
| `snippet_chars < 0` | 400 |
| File deleted between DB hit and snippet read | `snippet: ""` (do NOT remove hit) |
| File unreadable (permission) | `snippet: ""`, WARN log |
| DB unavailable | 503 |
| Backwater unavailable (semantic only) | 503 with `detail: backwater unreachable` |

### Acceptance criteria
1. With fixture vault `tests/fixtures/snippet_vault/` containing `alpha.md` whose body is `"AAA BBB CCC " * 20` (no frontmatter), `GET /vault/semantic-search?q=alpha&snippet_chars=50` returns `snippet` of length ≤ 50, ending at a space (no mid-word).
2. With the same fixture's `beta.md` containing only `---\ntag: x\n---\n` (no body), snippet is `""`.
3. With `snippet_chars=0`, response objects have no `snippet` key (assert key absence, not empty string).
4. Deleting a file between sync and search returns the hit with `snippet: ""` and no 500.

### Observability
- INFO on success: `{route, request_id, result_kind: "ok", result_count: <n hits>, duration_ms, q_len: <len(q)>, snippet_chars}`.
- WARN on per-file snippet read failure: `{route, request_id, path, error_class}`.
- Verifiable from logs: 24h scan of `route=/vault/semantic-search` lines yields p50/p99 of `duration_ms` and shows nonzero `result_count` for non-trivial queries.


---

## 2. Batch note read

### Goal
Collapse N reads into one round-trip.

### Route
```
POST /vault/notes/batch
Body: {"paths": ["a.md", "b.md", "c.md"]}
```

### Constraints
- `paths` length: 1..50. Empty → 400. Over 50 → 400.
- Duplicates in `paths`: kept, processed once, response carries one entry per input position. (Caller's responsibility to dedup if they care; entry order matches input order.)
- Path-escape (`_resolve` raises) for any single path: that entry has `status: "error"`, `error: "path escapes vault"`. The batch does NOT fail. (Rationale: an agent debug-pasting `../etc/passwd` shouldn't take down its whole batch; the per-entry visibility is enough.)

### Response
```json
{
  "results": [
    {"path": "a.md", "status": "ok", "note": {"path": "a.md", "content": "...", "frontmatter": {}, "body": "...", "wikilinks": [], "tags": []}},
    {"path": "b.md", "status": "not_found", "error": "not found"},
    {"path": "c.md", "status": "error", "error": "<sanitized message>"}
  ],
  "summary": {"ok": 1, "not_found": 1, "error": 1}
}
```

### Semantics
- `status` ∈ `{ok, not_found, error}`. `ok` carries `note`; others carry `error` (a human-readable string).
- `not_found` carries `error: "not found"`. `error` carries a sanitized message: exactly `"path escapes vault"` for path-escape, or the exception class name (e.g., `"PermissionError"`) for other I/O failures. No absolute paths, no python tracebacks.
- `results` order matches `paths` order positionally.

### Failure modes
| Condition | Behavior |
|---|---|
| Empty `paths` | 400 |
| `paths` length > 50 | 400 |
| `paths` not a list | 422 (FastAPI default) |
| Whole vault unmounted mid-batch | per-entry I/O errors; no 500 |
| Total response > 10 MiB | response still returned (no cap); document risk |

### Acceptance criteria
1. Batch of `["exists.md", "missing.md", "../escape.md"]` returns 3 entries, `summary: {ok:1, not_found:1, error:1}`, and the escape entry's error is exactly `"path escapes vault"`.
2. Duplicate paths in input → duplicate entries in output, same order.
3. Empty `paths` → 400, no work performed (verified by log absence).

### Observability
- INFO on success: `{route, request_id, result_kind: "ok"|"partial", result_count: <total>, ok_count, not_found_count, error_count, duration_ms}`.
- `result_kind = "partial"` if any entry status ≠ ok.
- Verifiable from logs: per-day count of batches and per-batch ok-rate.

---

## 3. Recent / changed notes

### Goal
"What did the user touch since X?" without parsing git on the client.

### Route
```
GET /vault/changes?since=<iso8601-or-epoch>&days=<int>&limit=<int>&include_diff_stats=<bool>
```

Either `since` or `days`. If both → 400. If neither → `days=7`. `days` range 1..365. `limit` default 200, max 2000. `include_diff_stats=false` default.

### Backing
```
git -C <vault> log --since=<iso> --name-status --pretty=format:%H%x1f%ct%x1f%s%x1e
```

Optional with `include_diff_stats=true`:
```
git -C <vault> log --since=<iso> --numstat --pretty=format:%H%x1f%ct%x1f%s%x1e
```

Two parses run separately and are joined by commit hash if both flags are needed.

### Response
```json
{
  "since": 1779600000.0,
  "limit": 200,
  "changes": [
    {
      "path": "Middlegame Context.md",
      "change": "modified",
      "commit": "672697e",
      "timestamp": 1780115422.0,
      "subject": "merge",
      "from_path": null,
      "diff_stats": null
    }
  ],
  "truncated": false
}
```

### Semantics
- `change` ∈ `{added, modified, deleted, renamed, copied, type_changed}`.
- For `renamed`/`copied`, `path` is the destination; `from_path` is the source.
- Rename detection uses git's default `-M` threshold (50% similarity). Documented; not configurable.
- `.obsidian/` and `.trash/` prefixed paths are filtered server-side. No other paths filtered.
- `truncated: true` if total git output had more changes than `limit` (we count pre-cap).
- Merge commits: included. `subject` is the merge subject. Each file change in the merge appears as its own entry. (Yes, this can be noisy on merge-heavy repos — accepted.)

### Failure modes
| Condition | Behavior |
|---|---|
| Vault is not a git repo | 400 `{"detail": "vault is not a git repository"}` |
| `git` binary not installed | 500 `{"detail": "git not available on server"}` |
| Shallow clone older than `since` | Return what git gives; include `warning: "history may be shallow"` field |
| Subprocess timeout (10 s) | 504 |
| Filename with non-utf8 bytes | Entry omitted, WARN log with bytes-quoted name |
| `days=0` or negative | 400 |
| `since` un-parseable | 400 with example |
| `since` in the future | 200, empty `changes` |

### Acceptance criteria
1. With a fixture repo of 5 known commits, `?days=30` returns exactly the file changes from those commits in newest-first order.
2. A commit that renames `a.md` → `b.md` produces one entry with `change: "renamed"`, `path: "b.md"`, `from_path: "a.md"`.
3. `?limit=1` returns 1 entry and `truncated: true`.
4. `?days=0` returns 400.
5. `?since=tomorrow` returns 400 (un-parseable); `?since=<future epoch>` returns empty changes.

### Observability
- INFO on success: `{route, request_id, result_kind, result_count, duration_ms, days_or_since, truncated}`.
- WARN on shallow clone or non-utf8 filename.
- Verifiable from logs: count of `truncated=true` responses (signal that `limit` cap is too low).

---

## 4. Frontmatter / tag filtering on file listing

### Goal
Cut the 4110-file flat list down by tag / frontmatter / path prefix server-side.

### Route (changes existing)
```
GET /vault/files
  ?tag=<tag>         (repeatable, AND across repeats)
  &fm.<key>=<value>  (repeatable across DIFFERENT keys; same key repeated → 400)
  &path_glob=<pattern>
  &limit=<int>
```

Bare `GET /vault/files` (no filters) returns the existing shape unchanged.

### Response (when ANY filter present)
```json
{
  "files": [{"path": "Foo.md", "size": 1234}],
  "total": 12,
  "filtered_from": 4110
}
```

### Semantics
- `tag` matching uses the existing `extract_tags` util (frontmatter `tags:` field). Exact match per tag. Repeats → AND.
- `fm.<key>`: case-sensitive key match in frontmatter. Value matching rules:
  - Strings: byte-exact equality.
  - Booleans: literal strings `true`/`false` (case-sensitive) match Python `True`/`False`.
  - Numbers: query string parsed as float; matches if `float(value) == frontmatter_value`. (No NaN match.)
  - Dates parsed by YAML as `datetime.date`: caller passes ISO 8601 `YYYY-MM-DD`; we compare via `str(date_obj) == value`.
  - Lists: matches if ANY element equals (after str() cast).
  - Dicts: NO matching (filter ignored; WARN log; key returned with no matches).
- `fm.<key>` key may NOT contain a `.`. Nested-key filters are out of scope.
- Same `fm.<key>` repeated → 400 `{"detail": "duplicate filter key: fm.<key>"}`.
- `path_glob` matches the relative path using `pathlib.PurePosixPath().match(pattern)` semantics: `*` matches within one segment (does not cross `/`), `**` matches any number of segments, `?` matches one character, `[seq]` / `[!seq]` are character classes. Examples: `Work Docs/*.md` (direct children only), `Work Docs/**/*.md` (recursive), `Daily/2026-*.md` (date-prefix files in one folder), `**/*.md` (every markdown file, equivalent to no filter). Patterns with no wildcards must match the full path exactly.
- File with malformed YAML frontmatter (the existing util returns `({}, body)` silently) → treated as no frontmatter; never matches any `fm.*`.
- Filters compose: filtered set = files passing ALL filters.
- `limit` is applied after filtering.

### Failure modes
| Condition | Behavior |
|---|---|
| Same `fm.<k>` twice | 400 |
| `fm.<key>` with `.` in key | 400 `{"detail": "nested keys not supported"}` |
| `path_glob` parse error | 400 with the parse error message |
| `path_glob` contains `..` segment | 400 |
| Vault scan exceeds 30 s hard timeout | 504 |

### Acceptance criteria
1. Fixture vault with 3 notes tagged `foo`, 2 tagged `bar`, 1 tagged both: `?tag=foo&tag=bar` returns exactly 1 path; `total=1`, `filtered_from=<vault size>`.
2. `?fm.status=in-progress` returns only notes whose YAML frontmatter has `status: in-progress`.
3. `?fm.priority=3` matches notes with YAML `priority: 3` (integer in YAML).
4. `?fm.status=true` matches notes with `status: true`.
5. Bare `GET /vault/files` returns the legacy shape (no `total`, no `filtered_from`).
6. `?fm.status=x&fm.status=y` → 400.
7. `?path_glob=Work Docs/*.md` returns direct .md children of `Work Docs/` only; a fixture file at `Work Docs/Sub/x.md` is NOT in the result.
8. `?path_glob=Work Docs/**/*.md` includes both `Work Docs/foo.md` and `Work Docs/Sub/x.md`.
9. `?path_glob=Daily/2026-*.md` returns only Daily-folder notes whose filename starts with `2026-`.

### Observability
- INFO on success: `{route, request_id, result_kind: "ok", result_count: total, filtered_from, filter_keys: ["tag", "fm.status", ...], duration_ms}`.
- Verifiable from logs: ratio of `result_count`/`filtered_from` tells us how selective real filters are.

---

## 5. Anchored `replace` PATCH op

### Goal
A single edit primitive that LLM agents reliably hit on the first try. Mirrors the design of Claude Code's `Edit` tool and Aider's SEARCH/REPLACE blocks — both empirically the most successful LLM editing patterns shipped.

### Design rationale
LLM agents are excellent markdown parsers. They are mediocre at line-counting, position-based edits, and parsing rules a server invents. The least-friction primitive is: "I read the file, here is the exact text I want gone, here is what replaces it." All "section-aware" operations a previous draft of this spec listed (`replace_section`, `insert_under_heading`, `delete_section`, `prepend`) collapse into anchored replace, with the LLM doing its own structural reasoning on content it just read.

### Route (extends existing)
```
PATCH /vault/notes/{path:path}
Body: {"op": "<op>", ...op-specific fields}
```

### Op catalog (final)

| Op | Status | Idempotent |
|---|---|---|
| `append` | existing | no |
| `set_frontmatter` | existing | yes |
| `replace` | NEW | yes |

### Op spec

```json
{
  "op": "replace",
  "old": "<exact bytes to find>",
  "new": "<replacement bytes>",
  "replace_all": false
}
```

### Semantics
- Matching is byte-exact. No whitespace normalization. No case folding. No regex. The bytes in `old` must appear verbatim in the file content.
- File content for matching = the full file as written to disk, including frontmatter. The LLM is responsible for crafting an anchor that doesn't accidentally overlap frontmatter unless intended.
- `replace_all = false` (default): the match must be unique. Zero matches → 404. Two-or-more matches → 409 with `match_count: N` so the agent can widen the anchor and retry.
- `replace_all = true`: every occurrence is replaced. Response includes `replacements: N`. Zero matches → 404 (still — caller asked for `_all` but there's nothing to replace; explicit failure is more useful than silent no-op).
- The replacement is done by `content.replace(old, new, count=1)` for unique mode, `content.replace(old, new)` for replace_all mode. Python `str.replace` semantics throughout.
- No content-shape constraints. `old` and `new` may include newlines, leading/trailing whitespace, or be empty (`new=""` deletes the matched bytes; `old=""` is rejected as 400 to avoid a footgun).

### Composing patterns the old section-ops covered

| Old intent | New form |
|---|---|
| `replace_section "## Tasks"` | Read file, send `old="## Tasks\n<existing section body>\n## Next"` and `new="## Tasks\n<new body>\n## Next"`. |
| `insert_under_heading top` | `old="## Tasks\n"`, `new="## Tasks\n<inserted content>\n"`. |
| `insert_under_heading bottom` | Read file, find the section terminator line, send a replace anchoring that line with content inserted before it. |
| `delete_section` | `old="## Tasks\n<section body>\n## Next"`, `new="## Next"`. |
| `prepend` | `old="<first 80 chars of body>"`, `new="<prepended content>\n<first 80 chars of body>"`. Or just use existing PUT to rewrite the file. |

In every case, the LLM did the markdown reasoning on content it already had in context, and the server did one deterministic byte-substitution. No heading parser. No code-fence ambiguity. No "first match wins" warnings.

### Content size caps
- `old` > 1 MiB → 413.
- `new` > 1 MiB → 413.
- File after substitution > 10 MiB → 413 with `detail: "file would exceed 10 MiB"`.

### Failure modes
| Condition | Behavior |
|---|---|
| `old` empty | 400 `{"detail": "old must be non-empty"}` |
| `old` not found | 404 `{"detail": "old not found in file"}` |
| `old` matches > 1, `replace_all=false` | 409 `{"detail": "old matched N times; set replace_all=true or widen anchor", "match_count": N}` |
| `old` not found AND `replace_all=true` | 404 (explicit, not silent no-op) |
| File not found | 404 (path-level) |
| File is a directory | 400 |
| File changed between caller's read and PATCH | The PATCH still runs against the current file. If `old` no longer matches, 404. (No optimistic-concurrency token in v1; documented.) |
| Disk full mid-write | 500. File may be partially written. v1 has no atomic-write guarantee — accepted under single-user assumption. |
| `old` > 1 MiB or `new` > 1 MiB | 413 |
| Result file > 10 MiB | 413 |

### Response
Same shape as existing PATCH success: full updated note. Adds:
- `replacements: <int>` — 1 for unique-replace, N for replace_all.
- `match_count: <int>` — only on 409.

### Acceptance criteria
1. Fixture file `tests/fixtures/replace/simple.md` with body `"alpha beta gamma"`. PATCH `op=replace, old="beta", new="DELTA"` → response `replacements: 1`, file on disk reads `"alpha DELTA gamma"`.
2. Same file, PATCH `old="zeta", new="X"` → 404, file unchanged byte-for-byte.
3. Fixture with `"x x x"`, PATCH `old="x", new="y"` (replace_all=false) → 409 with `match_count: 3`, file unchanged.
4. Same fixture, PATCH `old="x", new="y", replace_all=true` → 200 with `replacements: 3`, file is `"y y y"`.
5. PATCH `old="", new="x"` → 400.
6. PATCH `old="foo", new=""` on file containing `"foo"` → 200, file content has `foo` deleted.
7. Multi-line `old` spanning a heading + section body replaces correctly. Verifies the "compose section-ops via replace" pattern.
8. `old` containing `\r\n` against a file with `\n` line endings → 404 (no normalization; documented).
9. Result file > 10 MiB → 413, source file unchanged.

### Observability
- INFO on success: `{route, request_id, op: "replace", result_kind: "ok", duration_ms, replacements, old_len: <int>, new_len: <int>, replace_all: <bool>}`.
- INFO on 409 (ambiguous match): `{route, request_id, op: "replace", result_kind: "ambiguous", match_count, old_len, duration_ms}`. Ambiguous-match is interesting telemetry — high rate means agents are giving too little context.
- INFO on 404 (no match): `{route, request_id, op: "replace", result_kind: "not_found", old_len, duration_ms}`.
- ERROR on disk-write failure.
- Verifiable from logs: rate of `result_kind: "ambiguous"` is the leading indicator of agent anchor quality. Rate of `result_kind: "not_found"` measures stale-read frequency.

---

## 6. Daily-note shortcuts

### Goal
The common write path (today's note) is one call, never 404s.

### Routes
```
GET    /vault/periodic/today
GET    /vault/periodic/yesterday
GET    /vault/periodic/by-date/{YYYY-MM-DD}
POST   /vault/periodic/today/append             {"content": "..."}
PATCH  /vault/periodic/today                    {"op": "...", ...}
```

### Semantics
- Date resolution: `BLACKGLASS_TZ` env var (IANA timezone, e.g. `America/Los_Angeles`). Defaults to `UTC` if unset. botvinnik runs UTC; set `BLACKGLASS_TZ=America/Los_Angeles` in `blackglass.env` to match the user's local day boundary.
- Daily-note filename: `YYYY-MM-DD.md` at vault root, where the date is "today in `BLACKGLASS_TZ`". Matches existing `_PERIODIC_RE`.
- `by-date/{YYYY-MM-DD}`: `YYYY-MM-DD` must match `_PERIODIC_RE`. Otherwise 400.
- `by-date` date range: 1970-01-01..2099-12-31. Outside → 400.
- All five routes auto-create the file if absent, as a 0-byte empty file. No frontmatter is generated.
- Auto-create writes via `pathlib.Path.touch(exist_ok=True)`. Race-safe at the open() level; the empty file is the deterministic state.
- `created: true` field in GET responses on the call that created the file. Subsequent calls return `created: false`.
- Auto-create does NOT commit to git. Next `/vault/sync` will pull (no-op if no upstream changes) and embedding sync sees the new file as needing indexing.

### Failure modes
| Condition | Behavior |
|---|---|
| Vault not writable | 503 `{"detail": "vault not writable"}` |
| Disk full on auto-create | 507 `{"detail": "no space on device"}` |
| Date format invalid | 400 |
| Date out of range | 400 |

### Acceptance criteria
1. GET `/vault/periodic/today` on a clean fixture vault (no `<today>.md`) returns `created: true`, then a second GET returns `created: false`. File exists on disk after first call.
2. POST `/vault/periodic/today/append` with content creates the file if missing, appends content. Two calls produce content appended twice.
3. GET `/vault/periodic/by-date/2026-13-01` → 400.
4. GET `/vault/periodic/by-date/1969-12-31` → 400.

### Observability
- INFO: `{route, request_id, result_kind: "ok", duration_ms, date: "YYYY-MM-DD", created: <bool>}`.
- Verifiable from logs: count of `created: true` events = days the user (or agent) first touched a new daily note.


---

## 7. Metadata-only fetch

### Goal
Cheap existence + frontmatter check without pulling the body.

### Route
```
GET /vault/notes/{path:path}/meta
```

### Response (always 200 if path is valid)
```json
{
  "path": "Middlegame Context.md",
  "exists": true,
  "size": 8423,
  "mtime": 1780115422.0,
  "frontmatter": {"status": "in-progress"},
  "tags": ["project-headwater"],
  "wikilinks_count": 7
}
```

### Semantics
- If `exists: false`: `size: 0`, `mtime: null`, `frontmatter: {}`, `tags: []`, `wikilinks_count: 0`.
- 200 even when the file is absent. Use existence check via the `exists` field, not via status code.
- Implementation reads the file once, parses frontmatter, scans body for wikilinks with `re.findall(r"\[\[", body)`. The count is total occurrences (NOT unique).
- Path escape: 400, before any file access.

### Failure modes
| Condition | Behavior |
|---|---|
| Path escape | 400 |
| Path is a directory | 400 `{"detail": "path is a directory"}` |
| File too large to stat (>2 GiB) | 200 with `size: <whatever stat returns>` (no special handling) |

### Acceptance criteria
1. Existing file: returns correct `size` (matches `stat`), `mtime`, frontmatter parsed.
2. Non-existing file: returns 200 with `exists: false` and zeroed fields.
3. Path escape: 400, no log of file access.
4. `wikilinks_count` counts every `[[` occurrence (verify with a fixture containing duplicate links).

### Observability
- INFO: `{route, request_id, result_kind: "ok", duration_ms, exists}`. Only logs on 5xx beyond that.

---

## 8. Move / rename

### Goal
Atomic-feeling rename + wikilink rewrite + embedding row update.

### Route
```
POST /vault/notes/{path:path}/move
Body: {"to": "new/path.md", "rewrite_links": true}
```

### Pre-flight (all checked before any disk write)
| Check | Failure response |
|---|---|
| source `_resolve` | 400 path escape |
| `to` `_resolve` | 400 |
| source not found | 404 |
| `to` already exists | 409 `{"detail": "destination exists"}` |
| `to` == source | 400 |
| `to` is a directory path (ends with `/`) | 400 |

If `to`'s parent directory is missing, the move creates it (`mkdir -p` semantics).

### Order of operations (NOT transactional)
1. Resolve old/new stem.
2. `os.rename(old, new)`.
3. Update DB: `UPDATE vault_embeddings SET path=$new WHERE path=$old`. If `vault_embeddings` already has a row at the new path (orphan from a prior move), the existing row is DELETED first within the same transaction.
4. If `rewrite_links=true`: scan `.md` files (skipping `.obsidian`, `.trash`, and the moved file itself), apply the wikilink rewrites listed below. Each successful file rewrite is appended to `rewrote_links_in`. Each failure to one file (read error, write error) is appended to `rewrite_errors` with `{path, error_class}`. The scan never raises; partial success is reported.

### Wikilink rewrites (precisely scoped — v1)

| Pattern | Action |
|---|---|
| `[[<old_stem>]]` | `[[<new_stem>]]` |
| `[[<old_stem>\|<alias>]]` | `[[<new_stem>\|<alias>]]` |
| `[[<old_stem>#<anchor>]]` | `[[<new_stem>#<anchor>]]` |
| `[[<old_stem>#<anchor>\|<alias>]]` | `[[<new_stem>#<anchor>\|<alias>]]` |
| `![[<old_stem>]]` (embed) | `![[<new_stem>]]` |
| `![[<old_stem>#<anchor>]]` | `![[<new_stem>#<anchor>]]` |
| Block reference `[[<old_stem>#^<block>]]` | `[[<new_stem>#^<block>]]` |
| Full-path wikilink `[[<old_full_rel_path_without_ext>]]` | Rewritten if exact match |

### Stem collision (the real footgun)
- `old_stem` is `Path(old).stem`. If multiple notes share that stem at different paths, EVERY `[[<old_stem>]]` matches naively, regardless of which note it pointed to.
- v1 behavior: rewrite ALL of them. WARN in response with `stem_collision: true` and list of OTHER notes sharing that stem at move time.
- Caller is told (via the warning) to audit.

### Response
```json
{
  "from": "old/path.md",
  "to": "new/path.md",
  "rewrote_links_in": ["a.md", "b.md"],
  "rewrite_errors": [{"path": "c.md", "error_class": "PermissionError"}],
  "embedding_updated": true,
  "stem_collision": false,
  "stem_collision_paths": []
}
```

### Failure modes
| Condition | Behavior |
|---|---|
| Source missing | 404 |
| Dest exists | 409 |
| Rename fails (permission) | 500 — DB and rewrites NOT executed |
| Rename succeeds, DB fails | 200 with `embedding_updated: false`, `db_error` field with class name; sync will heal on next run |
| Rename + DB succeed, rewrite scan fails partway | 200 with `rewrite_errors` populated |
| Stem collision exists | 200 with `stem_collision: true` |
| `to` parent doesn't exist | mkdir -p, then proceed |

### Acceptance criteria
1. Move `a.md` → `b.md` with no other refs: response shows `rewrote_links_in: []`, both `os.path.exists("a.md") == False` and `b.md` exists.
2. Move `a.md` → `b.md` with two other notes containing `[[a]]`: response shows those two paths, files on disk have `[[b]]`.
3. Move with stem collision (two notes have stem `foo`): response has `stem_collision: true`, `stem_collision_paths: [<other path>]`.
4. Embed pattern `![[a]]` is rewritten to `![[b]]`.
5. Heading-anchored `[[a#h]]` becomes `[[b#h]]`.
6. Dest exists → 409, source still on disk.
7. DB embedding row is moved (verified by SELECT after).

### Observability
- INFO on success: `{route, request_id, result_kind, from, to, rewrote_links_count, rewrite_error_count, embedding_updated, stem_collision, duration_ms}`.
- WARN on stem collision.
- ERROR on rename failure or DB failure.
- Verifiable from logs: count of moves and their average `rewrote_links_count`.

### Notes
- Frontmatter `aliases:` entries are NOT rewritten (aliases reflect user intent, not link references).
- Block references without a note prefix (`[[#^block-id]]`) are note-local and out of scope.
- No background embedding re-run after move: the DB row is updated in step 3 above; file content is unchanged so the embedding remains valid.

---

## 9. Hybrid text + semantic search

### Goal
One search call that combines text and semantic recall.

### Route
```
GET /vault/hybrid-search?q=<query>&limit=<int>&snippet_chars=<int>&k=<int>
```

Defaults: `limit=10`, `snippet_chars=300`, `k=60`.

### Algorithm
1. Run text search and semantic search in parallel, each requesting `limit * 3` candidates.
2. For each unique path, score = `sum_over_subsearches(1 / (k + rank))` where `rank` is 1-indexed within that subsearch's result list.
3. Sort by score descending, take top `limit`.
4. Compute snippet for each surviving hit. Preference order:
   - If `text_rank` is not null AND text search returned a match excerpt, use the text excerpt.
   - Else use the body preamble (same logic as feature 1).

### Response
```json
[
  {
    "path": "Middlegame NOC.md",
    "score": 0.0312,
    "snippet": "...",
    "sources": ["text", "semantic"],
    "text_rank": 3,
    "semantic_rank": 1
  }
]
```

### Semantics
- `score` is the RRF score; not comparable across queries, not normalized.
- `sources` is sorted alphabetically for determinism.
- If text search returns zero hits, only semantic contributes. `sources: ["semantic"]`.
- If semantic search returns zero hits (e.g., DB empty), only text contributes.
- If both return zero: empty list, no error.

### Failure modes
| Condition | Behavior |
|---|---|
| Backwater unreachable | Try text-only; response has `degraded: "semantic_unavailable"` field |
| DB unreachable | 503 |
| `q` empty | 400 |
| `k < 1` or `k > 1000` | 400 |

### Acceptance criteria
1. Fixture vault with known notes: query `q="middlegame"` returns deterministic ordering given fixed seed.
2. `k=1` vs `k=60` produces different orderings (sanity check that `k` is wired).
3. Note appearing in both text and semantic results has `sources: ["semantic", "text"]` (alphabetic).
4. Empty query → 400.
5. With backwater stubbed down → response has `degraded` field, only text results.

### Observability
- INFO: `{route, request_id, result_kind, result_count, duration_ms, text_count, semantic_count, degraded: <str|null>}`.
- WARN when `degraded != null`.
- Verifiable from logs: ratio of degraded responses is the SLO for backwater availability from blackglass's perspective.

---

## Implementation order (revised)

1. Snippets in `semantic-search` + `search` (lowest risk, depended on by hybrid)
2. Meta-only fetch (smallest standalone feature)
3. Batch read
4. Daily-note shortcuts
5. Frontmatter/tag filtering on `/vault/files`
6. Recent/changes
7. `replace` PATCH op (smallest correctness surface of any feature: byte-exact substring replace)
8. Hybrid search (composes 1 + existing routes)
9. Move + wikilink rewrite (touches DB + filesystem + scans everything; last)

## Resolved decisions (v3)

All v2 open questions resolved by the user:

1. Snippet default `snippet_chars=300`.
2. Daily-note timezone via `BLACKGLASS_TZ` env var (default `UTC`).
3. Move does NOT rewrite frontmatter `aliases:`.
4. Move silently deletes orphan DB rows at the destination path.
5. Hybrid search snippet prefers the text-match excerpt when available, falls back to body preamble.
6. `/vault/files` uses `path_glob` (pathlib semantics: `*` per segment, `**` recursive), NOT prefix-only.
7. Performance budgets accepted as drafted; revisit after measurement.
8. `replace` op does NOT include `if_hash` opportunistic-concurrency token in v1.

Recheck before plan-writing: any of the above the user wants to revisit.
