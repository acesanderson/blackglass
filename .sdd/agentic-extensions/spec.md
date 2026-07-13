# Agentic Extensions

**Status:** DONE
**Source:** `docs/specs/2026-05-30-agentic-extensions.md` (v3, post-review)

---

## Goal

Close the worst friction points an LLM agent hits when reading and writing the vault through blackglass: too many round-trips, too many tokens per round-trip, no way to ask "what changed," weak PATCH ops, no atomic rename, and no merged ranking across text + semantic search. Nine features, each targeting a specific agent friction point.

## Interface / Scope

### What the user/system sees

Nine new or extended API endpoints:

1. **Snippets in search** — `GET /vault/search` and `GET /vault/semantic-search` gain `snippet_chars` param; response objects include `snippet` field
2. **Batch note read** — `POST /vault/notes/batch` collapses N reads into one round-trip (max 50 paths)
3. **Recent/changed notes** — `GET /vault/changes` answers "what changed since X?" without client-side git parsing
4. **Frontmatter/tag filtering** — `GET /vault/files` gains `tag`, `fm.<key>`, `path_glob`, `limit` filter params
5. **Anchored replace PATCH op** — `PATCH /vault/notes/{path}` with `op: "replace"` for byte-exact find-and-replace
6. **Daily-note shortcuts** — 5 routes for today/yesterday/by-date access with auto-create
7. **Metadata-only fetch** — `GET /vault/notes/{path}/meta` for cheap existence + frontmatter check
8. **Move/rename with wikilink rewrite** — `POST /vault/notes/{path}/move` with automatic wikilink rewriting
9. **Hybrid text + semantic search** — `GET /vault/hybrid-search` via Reciprocal Rank Fusion

### In scope

- All new server endpoints and parameter extensions
- CLI verbs for every new endpoint (covered by cli-full-coverage spec)
- Performance budgets, error handling, observability for all features
- Cross-cutting concerns: additive versioning, idempotency, payload caps, security

### Out of scope

- Chunked embeddings or per-section vectors (current 2000-char truncation stays)
- Concurrency control / multi-writer locking (single-user assumption)
- Templates engine for daily notes (auto-create produces empty file)
- Undo, soft-delete, trash bin (recovery via `git checkout`)
- Server-side markdown structure parsing for edits
- Tag-prefix or hierarchy matching (`tag=foo/*`); exact match only
- Transactional/atomic move (multi-step with partial-failure reporting)
- Multi-vault (single `BLACKGLASS_VAULT_PATH`)
- Schema migration of existing embeddings
- Rate limiting / quota (single tenant)
- Backwards-compatibility shims (additive routes only)

## Non-goals

1. **Chunked embeddings or per-section vectors.** Current `_MAX_EMBED_CHARS = 2000` truncation stays. Long-doc recall loss is accepted.
2. **Concurrency control / multi-writer locking.** Single-user vault assumption.
3. **Templates engine for daily notes.** Auto-create produces an empty file (0 bytes).
4. **Undo, soft-delete, trash bin.** Recovery is via `git checkout`; agents must be told this and not invent their own.
5. **Server-side markdown structure parsing for edits.** PATCH edits use anchored find-and-replace. The LLM is a better markdown parser than any line-counting code we'd ship. No `replace_section`, no `insert_under_heading`, no code-fence awareness — by deliberate design, not omission.
6. **Tag-prefix or hierarchy matching** (`tag=foo/*`). Exact tag match only.
7. **Transactional/atomic move.** Move is a multi-step operation with partial-failure reporting; rollback is the caller's job.
8. **Multi-vault.** Single `BLACKGLASS_VAULT_PATH`.
9. **Schema migration of existing embeddings.** Sync re-indexes on hash mismatch only.
10. **Rate limiting / quota.** Single tenant.
11. **Backwards-compatibility shims.** Additive routes only; existing routes gain optional fields.

## Design Decisions

### 1. Anchored replace over section-aware ops

**Decision:** The `replace` PATCH op uses byte-exact find-and-replace (`old` → `new`) rather than section-aware operations (`replace_section`, `insert_under_heading`, `delete_section`).

**Trade-off:** This was the biggest design pivot (v3 pivot from v2's section-ops approach). Section-aware ops require a heading parser, code-fence awareness, and rules the server invents — all brittle and incomplete. LLM agents are excellent markdown parsers and already have the file content in context. "Here is the exact text I want gone, here is what replaces it" is the least-friction primitive. All section-level edits can be composed via anchored replace with the LLM doing structural reasoning on content it just read. This mirrors Claude Code's `Edit` tool and Aider's SEARCH/REPLACE blocks — both empirically the most successful LLM editing patterns shipped.

Composing old section-ops via replace:
- `replace_section` → read file, send `old="## Tasks\n<body>\n## Next"` / `new="## Tasks\n<new>\n## Next"`
- `insert_under_heading` → `old="## Tasks\n"` / `new="## Tasks\n<inserted>\n"`
- `delete_section` → `old="## Tasks\n<body>\n## Next"` / `new="## Next"`
- `prepend` → `old="<first 80 chars>"` / `new="<prepended>\n<first 80 chars>"` (or just PUT)

In every case, the LLM did the markdown reasoning on content it already had in context, and the server did one deterministic byte-substitution. No heading parser. No code-fence ambiguity. No "first match wins" warnings.

### 2. Byte-exact matching (no normalization)

**Decision:** `replace` op matching is byte-exact. No whitespace normalization, no case folding, no regex. `\r\n` vs `\n` mismatches are NOT normalized.

**Trade-off:** Agents must craft anchors that match the file exactly, including line endings. But normalization would hide bugs and make the behavior unpredictable. If an agent reads a file with `\n` endings, it should send `\n` in the anchor. The Python `str.replace` semantics apply throughout — `content.replace(old, new, count=1)` for unique mode, `content.replace(old, new)` for replace_all mode.

### 3. Unique-match semantics with 409 on ambiguity

**Decision:** `replace_all=false` (default): zero matches → 404, two+ matches → 409 with `match_count: N`. `replace_all=true`: replaces every occurrence, zero matches → 404 (explicit failure, not silent no-op).

**Trade-off:** Returning 404 on zero matches even with `replace_all=true` is slightly unusual — a no-op could be considered success. But explicit failure is more useful: the agent knows its anchor was wrong and can retry. The 409 with `match_count` gives the agent exactly the information it needs to widen the anchor and retry. `old=""` is rejected as 400 (prevents a footgun). `new=""` deletes the matched bytes.

### 4. RRF for hybrid search

**Decision:** Hybrid search uses Reciprocal Rank Fusion: `score = sum(1 / (k + rank))` where rank is 1-indexed within each subsearch. Default `k=60`. Runs text and semantic search in parallel, each requesting `limit * 3` candidates.

**Trade-off:** RRF is well-understood and doesn't require normalizing scores across different search backends (text scores and embedding distances are in different scales). The `k` parameter controls how much weight lower-ranked results get — `k=1` favors top results heavily, `k=60` is more democratic. Exposed as a param for experimentation. Snippet preference: if text search returned a match excerpt, use it; else use body preamble.

Graceful degradation: if backwater (semantic backend) is unreachable, fall back to text-only with `degraded: "semantic_unavailable"` in the response. If both return zero, empty list (no error).

### 5. Auto-create daily notes

**Decision:** All periodic endpoints auto-create the file if absent (0-byte empty file via `pathlib.Path.touch(exist_ok=True)`). No frontmatter is generated. Auto-create does NOT commit to git.

**Trade-off:** Creating empty files means agents never get 404 when working with today's note — the common write path is one call. The trade-off is empty files accumulating if the agent creates but never writes. Git sync handles this naturally. `created: true` field in GET responses on the call that created the file; subsequent calls return `created: false`.

Date resolution: `BLACKGLASS_TZ` env var (IANA timezone, e.g., `America/Los_Angeles`). Defaults to `UTC`. Daily-note filename: `YYYY-MM-DD.md` at vault root.

### 6. Stem collision warning on move

**Decision:** When rewriting wikilinks after a move, if multiple notes share the same stem (e.g., `Folder/foo.md` and `Other/foo.md`), ALL `[[foo]]` links are rewritten. Response includes `stem_collision: true` and `stem_collision_paths`.

**Trade-off:** Naive rewriting of all same-stem links is potentially incorrect — some `[[foo]]` links might have pointed to the other note. But disambiguating requires context the server doesn't have. The warning tells the agent to audit. This is the pragmatic v1 approach.

Wikilink rewrite patterns (v1):
- `[[old_stem]]` → `[[new_stem]]`
- `[[old_stem|alias]]` → `[[new_stem|alias]]`
- `[[old_stem#anchor]]` → `[[new_stem#anchor]]`
- `![[old_stem]]` (embed) → `![[new_stem]]`
- `[[old_stem#^block]]` → `[[new_stem#^block]]`
- Full-path wikilink `[[old_full_rel_path_without_ext]]` → rewritten if exact match

Frontmatter `aliases:` entries are NOT rewritten (aliases reflect user intent, not link references).

### 7. Snippet computation from body preamble

**Decision:** Snippets are computed by: read file → strip frontmatter → take `body[:snippet_chars + 100]` → find word boundary within 50 chars of limit → hard-truncate if no boundary found. Default `snippet_chars=300`. `snippet_chars=0` suppresses the `snippet` key entirely (not empty string).

**Trade-off:** Frontmatter is always stripped for snippet computation, so snippets always show content. Reading 100 extra chars for word-boundary detection avoids mid-word cutoffs. `snippet_chars=0` removing the key (rather than returning empty string) saves bandwidth. File missing/unreadable when computing snippet → `snippet: ""` (hit still returned; DB row is source of truth for relevance).

### 8. Metadata-only fetch returns 200 even when file absent

**Decision:** `GET /vault/notes/{path}/meta` returns 200 with `exists: false` and zeroed fields when the file doesn't exist. Existence check via the `exists` field, not via status code.

**Trade-off:** Unusual for a GET to return 200 for a missing resource. But the endpoint is specifically designed for existence checks — returning 404 would force agents to handle two code paths for the same "does this exist?" question. The response includes `path`, `exists`, `size`, `mtime`, `frontmatter`, `tags`, `wikilinks_count`. When `exists: false`: all fields are zeroed. `wikilinks_count` counts every `[[` occurrence (NOT unique).

### 9. Additive versioning (no breaking changes)

**Decision:** All new routes are additive. Existing routes gain optional fields only when new params are supplied. Bare `GET /vault/files` returns legacy shape unchanged.

**Trade-off:** Clients that strict-validate response schemas must adopt unknown-field tolerance. This is documented as a soft break. The alternative — versioned API paths (`/v2/...`) — is overkill for additive fields. The bare endpoint preserving its old shape means existing consumers are unaffected unless they opt into new params.

### 10. Move is multi-step, not transactional

**Decision:** Move order: (1) resolve paths via `_resolve`, (2) `os.rename(old, new)`, (3) update DB embeddings row, (4) scan + rewrite wikilinks. Each step can partially fail.

**Trade-off:** Partial failure means the vault can be in an inconsistent state (file moved but links not rewritten). Under the single-user assumption, the agent can retry or fix manually. A transactional approach would require distributed locking across filesystem + DB + all vault files, disproportionate complexity. DB failure after rename → 200 with `embedding_updated: false` and `db_error` field; sync will heal on next run. Rewrite errors → 200 with `rewrite_errors` populated (each entry has `{path, error_class}`).

Pre-flight checks (all before any disk write): source `_resolve`, `to` `_resolve`, source exists, `to` doesn't exist, `to` ≠ source, `to` not a directory. If `to`'s parent is missing, mkdir -p. Orphan DB rows at destination are deleted before insert.

## Changes

### New routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/vault/notes/batch` | POST | Batch read (max 50 paths, per-entry status) |
| `/vault/changes` | GET | Recent/changed notes via `git log` |
| `/vault/notes/{path}/meta` | GET | Metadata-only fetch (existence, size, frontmatter, tags, wikilinks_count) |
| `/vault/notes/{path}/move` | POST | Move/rename with wikilink rewrite + embedding update |
| `/vault/hybrid-search` | GET | Hybrid text + semantic search via RRF |
| `/vault/periodic/today` | GET | Today's daily note (auto-create) |
| `/vault/periodic/yesterday` | GET | Yesterday's daily note (auto-create) |
| `/vault/periodic/by-date/{YYYY-MM-DD}` | GET | Daily note by date (auto-create) |
| `/vault/periodic/today/append` | POST | Append content to today's note |
| `/vault/periodic/today` | PATCH | PATCH ops on today's note (append, prepend, set_frontmatter, replace) |

### Modified routes

| Route | Change |
|-------|--------|
| `GET /vault/search` | Gains `snippet_chars` param (default 300), response includes `snippet` field |
| `GET /vault/semantic-search` | Gains `snippet_chars` param, response includes `snippet` |
| `GET /vault/files` | Gains `tag` (×N, AND), `fm.<key>=<value>` (×N, different keys), `path_glob`, `limit`; response gains `total`/`filtered_from` when filters present |
| `PATCH /vault/notes/{path}` | Gains `op: "replace"` with `old`/`new`/`replace_all` fields |

### Key implementation files

| File | Changes |
|------|---------|
| `routes/notes.py` | Batch read endpoint, metadata-only fetch, move/rename with wikilink rewrite, anchored replace PATCH op |
| `routes/search.py` | Snippet computation in search results, hybrid search endpoint |
| `routes/vault.py` | Changes endpoint (git log parsing), frontmatter/tag/path_glob filtering on files endpoint |
| `routes/periodic.py` | Daily-note shortcuts with auto-create, timezone resolution via `BLACKGLASS_TZ` |
| `utils/snippets.py` | Snippet computation: frontmatter stripping, word-boundary truncation |
| `utils/hybrid.py` | RRF scoring: `sum(1/(k+rank))`, parallel execution, snippet preference |
| `utils/wikilinks.py` | Wikilink regex patterns for all rewrite forms, stem extraction |
| `middleware.py` | Structured logging additions for all new routes |
| `config.py` | `BLACKGLASS_TZ` env var handling |

### Cross-cutting implementations

**Idempotency table:**

| Route | Idempotent? | Notes |
|-------|-------------|-------|
| `GET /*` | yes | |
| `POST /vault/notes/batch` | yes | Read-only despite POST verb |
| `POST /vault/notes/{p}/move` | NO | Second call → 404 (source gone) |
| `PATCH` op=append | NO | Concatenates each call |
| `PATCH` op=replace (replace_all=false) | YES | 404 on second call after success |
| `PATCH` op=replace (replace_all=true) | YES | No-op on second call |
| `PATCH` op=set_frontmatter | YES | |
| `POST /vault/periodic/today/append` | NO | Concatenates each call |

**Performance budgets (p99, single-user load):**

| Route | Target | Hard timeout |
|-------|--------|--------------|
| `GET /vault/notes/{p}/meta` | 50 ms | 5 s |
| `GET /vault/semantic-search` (with snippet) | 500 ms | 30 s |
| `GET /vault/search` (with snippet) | 1 s | 30 s |
| `POST /vault/notes/batch` (50 paths) | 1 s | 30 s |
| `GET /vault/changes` (days≤30) | 1 s | 10 s |
| `GET /vault/files` (any filter) | 2 s | 30 s |
| `POST /vault/notes/{p}/move` (rewrite=true) | 3 s | 60 s |
| `GET /vault/hybrid-search` | 1 s | 30 s |
| `PATCH /vault/notes/{p}` (any op) | 500 ms | 30 s |

Routes exceeding hard timeout return 504. Subprocess calls (git, journalctl) invoked with `timeout=` matching the hard limit.

**Payload caps:**

| Field | Cap | Response |
|-------|-----|----------|
| PATCH `content` | 1 MiB | 413 |
| Batch `paths` | 50 items | 400 |
| Snippet length | 1000 chars | 400 |
| Replace `old`/`new` | 1 MiB each | 413 |
| Result file after replace | 10 MiB | 413 |

**Security:**

- Path traversal: `_resolve` is the single chokepoint. Every new route MUST call it for path inputs. No new code may `open(vault_path / x)` without `_resolve` first.
- Move `to` is `_resolve`d. A `to` outside the vault → 400.
- PATCH/POST content written verbatim. No HTML/JS sanitization.
- Auth on `/logs/journal` is non-negotiable — journal output leaks request paths and bodies.

**Observability requirements:**

Every new endpoint emits structured INFO on success and WARN/ERROR on failure:
```json
{
  "route": "<route name>",
  "request_id": "<correlation ID from middleware>",
  "result_kind": "ok | not_found | error | partial",
  "result_count": "<int, where meaningful>",
  "duration_ms": "<float>"
}
```

Per-feature `extra` fields are listed in each feature. Each feature's acceptance criteria includes a "verifiable from logs alone" line. `/status` is extended with `recent_op_counts`: rolling 1-hour counter per route from ring buffer.

**Error response shape:** All errors use `{detail: "<string>"}` unless an endpoint specifies otherwise (e.g., batch read returns 200 with per-item status). 4xx is client error, 5xx is server error, 504 is timeout.

## Acceptance Criteria

### 1. Snippets in search

1. Fixture vault with `alpha.md` (body = `"AAA BBB CCC " * 20`, no frontmatter): `GET /vault/semantic-search?q=alpha&snippet_chars=50` returns `snippet` of length ≤ 50, ending at a space (no mid-word cutoff).
2. `beta.md` containing only `---\ntag: x\n---\n` (no body): snippet is `""`.
3. `snippet_chars=0`: response objects have no `snippet` key (assert key absence, not empty string).
4. Deleting a file between sync and search returns the hit with `snippet: ""` and no 500.
5. `snippet_chars > 1000` → 400. `snippet_chars < 0` → 400. `q` empty → 400.

### 2. Batch note read

6. Batch of `["exists.md", "missing.md", "../escape.md"]` returns 3 entries, `summary: {ok:1, not_found:1, error:1}`, and the escape entry's error is exactly `"path escapes vault"`.
7. Duplicate paths in input → duplicate entries in output, same order.
8. Empty `paths` → 400, no work performed (verified by log absence).
9. `paths` length > 50 → 400.
10. Per-item `status` ∈ `{ok, not_found, error}`. `ok` carries `note`; others carry `error` string.

### 3. Recent/changed notes

11. Fixture repo of 5 known commits: `?days=30` returns exactly the file changes from those commits in newest-first order.
12. A commit that renames `a.md` → `b.md` produces one entry with `change: "renamed"`, `path: "b.md"`, `from_path: "a.md"`.
13. `?limit=1` returns 1 entry and `truncated: true`.
14. `?days=0` → 400.
15. `?since=tomorrow` → 400 (un-parseable); `?since=<future epoch>` → 200 with empty `changes`.
16. Vault not a git repo → 400.

### 4. Frontmatter/tag filtering

17. Fixture vault with 3 notes tagged `foo`, 2 tagged `bar`, 1 tagged both: `?tag=foo&tag=bar` returns exactly 1 path; `total=1`, `filtered_from=<vault size>`.
18. `?fm.status=in-progress` returns only notes with matching frontmatter.
19. `?fm.priority=3` matches notes with YAML `priority: 3` (integer in YAML).
20. `?fm.status=true` matches notes with `status: true`.
21. Bare `GET /vault/files` returns legacy shape (no `total`, no `filtered_from`).
22. `?fm.status=x&fm.status=y` → 400 (duplicate filter key).
23. `?path_glob=Work Docs/*.md` returns direct .md children only; `Work Docs/Sub/x.md` NOT included.
24. `?path_glob=Work Docs/**/*.md` includes both direct and nested children.
25. `?path_glob=Daily/2026-*.md` returns only Daily-folder notes whose filename starts with `2026-`.

### 5. Anchored replace

26. Fixture `"alpha beta gamma"`: PATCH `old="beta", new="DELTA"` → `replacements: 1`, file reads `"alpha DELTA gamma"`.
27. PATCH `old="zeta"` → 404, file unchanged byte-for-byte.
28. Fixture `"x x x"`: PATCH `old="x", new="y"` (replace_all=false) → 409 with `match_count: 3`, file unchanged.
29. Same fixture: PATCH `old="x", new="y", replace_all=true` → 200 with `replacements: 3`, file is `"y y y"`.
30. PATCH `old="", new="x"` → 400.
31. PATCH `old="foo", new=""` → 200, `foo` deleted from file content.
32. Multi-line `old` spanning heading + section body replaces correctly (composing section-ops via replace pattern).
33. `old` containing `\r\n` against a file with `\n` → 404 (no normalization).
34. Result file > 10 MiB → 413, source file unchanged.

### 6. Daily-note shortcuts

35. GET `/vault/periodic/today` on clean vault returns `created: true`; second GET returns `created: false`. File exists on disk after first call.
36. POST `/vault/periodic/today/append` with content creates file if missing, appends content. Two calls produce content appended twice.
37. GET `/vault/periodic/by-date/2026-13-01` → 400.
38. GET `/vault/periodic/by-date/1969-12-31` → 400.
39. Vault not writable → 503.

### 7. Metadata-only fetch

40. Existing file: returns correct `size` (matches `stat`), `mtime`, frontmatter parsed.
41. Non-existing file: returns 200 with `exists: false`, `size: 0`, `mtime: null`, `frontmatter: {}`, `tags: []`, `wikilinks_count: 0`.
42. Path escape: 400, no log of file access.
43. `wikilinks_count` counts every `[[` occurrence (verify with fixture containing duplicate links).

### 8. Move/rename with wikilink rewrite

44. Move `a.md` → `b.md` with no other refs: response shows `rewrote_links_in: []`, source gone, dest exists.
45. Move `a.md` → `b.md` with two notes containing `[[a]]`: response shows those two paths, files on disk have `[[b]]`.
46. Move with stem collision: response has `stem_collision: true`, `stem_collision_paths` lists other paths.
47. Embed pattern `![[a]]` → `![[b]]`.
48. Heading-anchored `[[a#h]]` → `[[b#h]]`.
49. Dest exists → 409, source still on disk.
50. DB embedding row is moved (verified by SELECT after).
51. Source == dest → 400.
52. `to` parent directory missing → mkdir-p then proceed.

### 9. Hybrid search

53. Known fixture vault: query `q="middlegame"` returns deterministic ordering given fixed seed.
54. `k=1` vs `k=60` produces different orderings (sanity check that `k` is wired).
55. Note in both text and semantic results has `sources: ["semantic", "text"]` (alphabetic).
56. Empty query → 400.
57. Backwater stubbed down → response has `degraded` field, only text results.
58. `k < 1` or `k > 1000` → 400.
