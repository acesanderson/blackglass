# Filesystem Aliases & Flat Vault Enforcement

**Status:** DONE
**Source:** `docs/specs/2026-06-28-filesystem-aliases.md`

---

## Goal

Make the Blackglass CLI interface familiar to LLMs by providing filesystem-style command aliases (`cat`, `ls`, `grep`, `find`, `tree`, etc.) while enforcing a flat vault structure (no subdirectories). The LLM should be able to navigate the vault using commands it already knows from shell training, without learning Blackglass-specific syntax for basic operations.

## Interface / Scope

### What the user/system sees

13 new top-level CLI aliases that map to existing server endpoints:

| Alias | Maps to | New syntax | Notes |
|-------|---------|-----------|-------|
| `cat` | `notes get` | `blackglass cat <path>` | Same behavior, shorter name |
| `ls` | `vault files` | `blackglass ls [path_glob] [--tag X] [--limit N]` | Optional positional glob replaces `--path-glob` |
| `head` | `notes get` + truncation | `blackglass head <path> [-n 10]` | New command. Client-side line slicing. |
| `tail` | `notes get` + offset | `blackglass tail <path> [-n 10]` | New command. Client-side line slicing. |
| `grep` | `search text` | `blackglass grep "pattern" [--limit N]` | `--limit` replaces `--snippet-chars` |
| `find` | `vault files --path-glob` | `blackglass find <glob>` | Positional glob, no `--path-glob` flag |
| `tree` | `vault files` (tree-formatted) | `blackglass tree [--depth N]` | New command. Client-side tree renderer. |
| `mv` | `notes move` | `blackglass mv <src> <dst>` | Same behavior, shorter name |
| `rm` | `notes delete` | `blackglass rm <path>` | Same behavior, shorter name |
| `stat` | `notes meta` | `blackglass stat <path>` | Same behavior, familiar name |
| `touch` | `notes create` (empty content) | `blackglass touch <path>` | Creates note with empty body |
| `cp` | `notes get` + `notes create` | `blackglass cp <src> <dst>` | New command. Reads src, creates dst. |
| `edit` | `notes replace` | `blackglass edit <path> --old "..." --new "..."` | Same behavior, shorter name |

Flat vault enforcement:
- **Server-side:** Write operations reject paths containing `/` (configurable via `flat: true` config, default on)
- **Client-side:** Read operations defensively strip directory prefixes with a warning to stderr
- **Path normalization:** Strips leading `/` and `~/`, validates flat, ensures `.md` extension

### In scope

- `blackglass-client` CLI: 13 alias commands + path normalization helper
- `blackglass-server` API: flat-path validation on write endpoints + config toggle
- Keeper template guidance for flat-path enforcement

### Out of scope

- Replicating arbitrary filesystem semantics (permissions, symlinks, inodes)
- Supporting subdirectory structures (vault is flat by design)
- Changing existing Blackglass command syntax (aliases are purely additive)
- New server-side search capabilities (`grep` maps to existing `search text`)
- Aliasing domain-specific commands (`periodic`, `obs`, `sync`, `backlinks`, `tags`)

## Non-goals

1. **Replicating arbitrary filesystem semantics.** Only the command names are borrowed. No permissions, symlinks, inodes, or ownership concepts.
2. **Supporting subdirectory structures.** The vault is flat by design. The Silt Framework requires flat vaults; enforcement prevents structural drift.
3. **Changing the existing Blackglass command syntax.** Aliases are purely additive — `notes get`, `search text`, etc. continue to work unchanged.
4. **Adding new server-side search capabilities.** `grep` maps to the existing `search text` endpoint. No regex engine, no context lines, no invert matching server-side.
5. **Aliasing domain-specific commands.** `periodic`, `obs`, `sync`, `backlinks`, `tags` have no clean filesystem equivalent and keep their current syntax.

## Design Decisions

### 1. Top-level aliases (not namespaced under `fs`)

**Decision:** Aliases live at the top level of the CLI: `blackglass cat`, not `blackglass fs cat`.

**Trade-off:** Risks future namespace collision if a Blackglass-native command is ever named `cat` or `ls`. Mitigated by the fact that filesystem commands are a closed set (13 commands, well-defined) and the namespace risk is low. Top-level placement is essential for the LLM familiarity goal — `blackglass fs cat` defeats the purpose because LLMs don't have `fs cat` in their training data. The alias namespace is documented as reserved.

### 2. Aliases are purely client-side (no new server routes)

**Decision:** All 13 aliases map to existing server endpoints. No new server routes are created for aliases. Four commands (`head`, `tail`, `tree`, `cp`) do client-side post-processing on top of existing endpoints.

**Trade-off:** `head` and `tail` fetch the full file and slice lines client-side, which is slightly wasteful for large files. But adding server-side line-range parameters would complicate the API for marginal gain — vault notes are typically small (under 100KB). `tree` renders client-side because the vault is always flat (single level). `cp` is two round-trips (get + create) rather than one atomic server operation, acceptable for the single-user case. The alternative — creating dedicated server endpoints for these — would add API surface for commands that are convenience wrappers.

### 3. Flat vault enforcement at both layers

**Decision:** Server-side validation rejects write paths containing `/` (configurable via `flat: true` config). Client-side defensively strips directory prefixes on read operations with a warning to stderr.

**Trade-off:** Defense in depth means two places to maintain the logic. But the layers serve different purposes: the server is the real enforcer (rejects bad writes that would create subdirectories); the client just handles the common LLM mistake of writing `Folder/Note.md` gracefully on reads. The config toggle (`flat: true/false`) allows disabling enforcement if the vault model ever changes or for testing.

Affected server endpoints (write operations):

| Endpoint | Method | Behavior |
|----------|--------|---------|
| `/vault/notes/{path}` | POST (create) | Reject if path contains `/` in stem |
| `/vault/notes/{path}` | PUT (update) | Reject if path contains `/` in stem |
| `/vault/notes/{path}` | DELETE | Reject if path contains `/` in stem |
| `/vault/notes/{path}/move` | POST | Reject if destination contains `/` |
| `/vault/notes/{path}/patch` | PATCH | Reject if path contains `/` in stem |

Read operations: no rejection. Paths with `/` return 404 (file not found at root) or are stripped by the CLI.

Server validation logic:
```python
def _validate_flat_path(path: str) -> str:
    stem = path.removesuffix(".md")
    if "/" in stem or "\\" in stem:
        raise HTTPException(400, f"Flat vault enforced. Paths must be root-level: {path}")
    return path
```

### 4. Path normalization helper

**Decision:** A `normalize_flat_path()` function handles all common LLM path mistakes: strips leading `/` and `~/`, validates flatness (no `/` in stem), and ensures `.md` extension.

```python
def normalize_flat_path(path: str) -> str:
    path = path.lstrip("/")
    path = path.removeprefix("~/")
    stem = path.removesuffix(".md")
    if "/" in stem or "\\" in stem:
        path = path.rsplit("/", 1)[-1]  # extract filename
        # CLI emits warning to stderr here
    if not path.endswith(".md"):
        path = path + ".md"
    return path
```

**Trade-off:** Automatically appending `.md` could surprise users who intentionally omit it. But in practice, every note in the vault has a `.md` extension, and LLMs frequently forget it. The normalization is applied before forwarding to the API, so the server always sees clean paths. The warning on directory stripping ensures the agent knows what happened.

Path normalization behavior:

| Input | Output | Warning |
|-------|--------|---------|
| `"Note.md"` | `"Note.md"` | none |
| `"/Note.md"` | `"Note.md"` | none |
| `"~/Note.md"` | `"Note.md"` | none |
| `"Folder/Note.md"` (read op) | `"Note.md"` | `WARN: Stripped directory prefix. Using 'Note.md' instead.` |
| `"Folder/Note.md"` (write op) | 400 rejection | server-side |
| `"Note"` | `"Note.md"` | none (auto-appended) |

### 5. Four new CLI-only commands

**Decision:** `head`, `tail`, `tree`, and `cp` are new commands that call existing endpoints with client-side post-processing.

**Implementation details:**

- **`head`** — Calls `notes get`, splits content on `\n`, takes first N lines (default 10 via `-n`/`--lines`), joins and prints.
- **`tail`** — Calls `notes get`, splits content on `\n`, takes last N lines (default 10 via `-n`/`--lines`), joins and prints.
- **`tree`** — Calls `vault files`, renders as indented tree with `├──` / `└──` characters. Always single level for flat vault. `--depth` flag accepted but effectively always 1 (forward-compatible).
- **`cp`** — Calls `notes get` on src, then `notes create` on dst with the retrieved content. Two round-trips, not atomic.

**Trade-off:** These are client-side compositions, not server features. This keeps the server API surface unchanged while providing the familiar commands. For `tree`, the `--depth` flag is a no-op in flat vaults but accepted to avoid breaking LLMs that habitually pass `--depth 2`. For `cp`, the two-round-trip nature means a failure between get and create could leave an incomplete copy — acceptable under single-user assumption.

Example `tree` output:
```
.
├── Postgres Indexing Notes.md
├── Silt Framework 2026-06-24.md
├── Silt Framework - Primitive - Atomic Note.md
├── Silt Framework - Primitive - Cluster.md
├── Silt Framework - Primitive - Domain.md
├── Silt Framework - Primitive - Todo.md
├── Silt Framework - Primitive - Wiki.md
└── Silt Framework - Primitive - Software Project.md
```

### 6. `grep` uses `--limit` not `--snippet-chars`

**Decision:** `blackglass grep "pattern" --limit N` maps to `search text` but exposes `--limit` (result count, default 10) rather than `--snippet-chars` (snippet length).

**Trade-off:** Less control over snippet size for the alias. But the `grep` alias is for quick searches where the default snippet (300 chars) is fine. Power users who need fine-grained snippet control use `search text --snippet-chars N` directly. The `--limit` flag matches what `grep` users expect (number of results).

### 7. `ls` accepts optional positional glob

**Decision:** `blackglass ls [path_glob]` accepts an optional positional argument that maps to the server's `--path-glob` query param. Also supports `--tag` and `--limit` flags.

**Trade-off:** Slightly unusual for a Click command to accept a positional that maps to a query param. But it matches LLM expectations perfectly — `ls Silt*` is natural shell syntax. The `--path-glob` flag still works for explicit use. When no positional is given, all files are listed (equivalent to `vault files` with no filters).

### 8. `cp` copies everything including frontmatter

**Decision:** `cp` calls `notes get` (which returns content including frontmatter) and `notes create` with that content. Frontmatter is copied as-is.

**Trade-off:** The user must manually edit frontmatter after copying if they want different metadata. But copying everything is the simpler default — partial copying would require a flag and frontmatter parsing, which is overkill for a convenience command. This matches Unix `cp` behavior (copies the whole file).

### 9. Commands that stay Blackglass-native

**Decision:** Domain-specific commands keep their current syntax with no aliases:

| Command | Why no alias |
|---------|-------------|
| `search semantic` | No filesystem equivalent for vector similarity |
| `search hybrid` | No filesystem equivalent for reciprocal rank fusion |
| `notes batch` | No filesystem equivalent for bulk reads |
| `notes set-frontmatter` | No filesystem equivalent for structured metadata |
| `notes append` / `prepend` | `tee -a` / `sed -i` are not clean analogs |
| `vault backlinks` | No filesystem equivalent |
| `vault tags` | No filesystem equivalent |
| `vault changes` | `git log` exists but different semantics |
| `vault sync` | No filesystem equivalent |
| `vault periodic` | Domain-specific |
| `obs *` | Domain-specific |

**Trade-off:** Inconsistency (some commands have aliases, some don't). But forcing filesystem metaphors onto non-filesystem concepts would create confusing aliases that don't match LLM training. The boundary is clean: if a shell command exists for it, alias it; otherwise keep the Blackglass-native name.

### 10. `touch` creates empty notes

**Decision:** `blackglass touch <path>` calls `notes create` with empty content string.

**Trade-off:** Unix `touch` updates timestamps on existing files or creates empty ones. This implementation only creates (doesn't update timestamps on existing notes). But the primary use case for agents is creating a note placeholder, and the server handles the "already exists" case with a 400. Matching the full `touch` semantics isn't worth the complexity.

## Changes

### Server-side changes

| File | Changes |
|------|---------|
| `blackglass-server/src/blackglass_server/config.py` | Added `flat: bool` config option (default: `true`) |
| `blackglass-server/src/blackglass_server/routes/notes.py` | Added `_validate_flat_path()` helper applied to all write endpoints (POST create, PUT update, DELETE, POST move, PATCH) |
| `blackglass-server/tests/test_flat_enforcement.py` | Tests: valid root path, rejected subdirectory path, edge cases (`.md` in directory name, encoded slashes, backslashes) |

### Client-side changes

| File | Changes |
|------|---------|
| `blackglass-client/src/blackglass_client/cli/aliases.py` | NEW — all 13 alias commands registered in the top-level Click group |
| `blackglass-client/src/blackglass_client/cli/_paths.py` | NEW — `normalize_flat_path()` helper |
| `blackglass-client/tests/test_aliases.py` | Tests for all aliases, path normalization, defensive stripping |

### Alias implementation summary

- **Simple passthroughs** (same endpoint, same behavior): `cat` → `notes get`, `mv` → `notes move`, `rm` → `notes delete`, `stat` → `notes meta`, `edit` → `notes replace`
- **Mapped with flag translation**: `ls` → `vault files` (positional glob → `--path-glob`), `grep` → `search text` (`--limit` → result count), `find` → `vault files --path-glob`
- **Client-side compositions** (new commands): `head`, `tail` (line slicing), `tree` (tree rendering), `cp` (get + create)
- **Special semantics**: `touch` (create with empty content)

### Keeper template guidance

Keepers that create or move notes must use root-level paths:
```python
path = path.lstrip("/")  # never absolute
if "/" in path.removesuffix(".md"):
    raise ValueError(f"Keeper attempted subdirectory path: {path}")
```

## Acceptance Criteria

### Alias correctness

1. `blackglass cat "Note.md"` returns note content, identical to `notes get`.
2. `blackglass ls` lists all root-level notes.
3. `blackglass ls "Silt*"` filters by glob pattern (maps to `--path-glob`).
4. `blackglass grep "pattern"` returns text search results as JSON.
5. `blackglass grep "pattern" --limit 5` limits to 5 results.
6. `blackglass find "Silt*"` returns matching filenames.
7. `blackglass tree` renders a flat tree with `├──` / `└──` characters.
8. `blackglass head "Note.md" -n 5` returns first 5 lines of the note.
9. `blackglass tail "Note.md" -n 5` returns last 5 lines of the note.
10. `blackglass touch "New.md"` creates an empty note.
11. `blackglass cp "A.md" "B.md"` copies content from A to B (including frontmatter).
12. `blackglass mv "A.md" "B.md"` renames with wikilink rewriting.
13. `blackglass rm "Note.md"` deletes the note.
14. `blackglass stat "Note.md"` returns metadata (size, mtime, frontmatter, tags, wikilinks_count).
15. `blackglass edit "Note.md" --old "X" --new "Y"` replaces text.

### Flat vault enforcement

16. `blackglass notes create "Folder/Note.md" --content "..."` returns 400 (server rejects subdirectory paths).
17. `blackglass notes create "Note.md" --content "..."` succeeds (root-level path).
18. `blackglass cat "Folder/Note.md"` strips prefix, warns to stderr, reads `Note.md`.
19. `blackglass cat "/Note.md"` strips leading `/`, reads `Note.md`.
20. `blackglass cat "~/Note.md"` strips `~/`, reads `Note.md`.
21. `blackglass cat "Note"` auto-appends `.md`, reads `Note.md`.
22. `flat: false` config disables server-side enforcement (subdirectory paths accepted).

### Backward compatibility

23. All existing commands (`notes get`, `search text`, `vault files`, etc.) continue to work unchanged.
24. `--help` for the top-level `blackglass` group lists all 13 aliases alongside existing groups.
25. No existing command names collide with the new aliases.
