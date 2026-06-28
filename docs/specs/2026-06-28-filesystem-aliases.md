# Blackglass Filesystem Aliases & Flat Vault Enforcement — Design Spec

**Status:** draft, v1
**Audience:** Claude Code / openclaw and similar agents using the blackglass CLI
**Scope:** `blackglass-client` CLI and `blackglass-server` API. Both changes required.

## Goal

Make the Blackglass CLI interface familiar to LLMs by providing filesystem-style command aliases (`cat`, `ls`, `grep`, `find`, `tree`, etc.) while enforcing a flat vault structure (no subdirectories). The LLM should be able to navigate the vault using commands it already knows from shell training, without learning Blackglass-specific syntax for basic operations.

## Non-goals

- Replicating arbitrary filesystem semantics (permissions, symlinks, inodes).
- Supporting subdirectory structures. The vault is flat by design.
- Changing the existing Blackglass command syntax. Aliases are additive.
- Adding new server-side search capabilities. `grep` maps to existing `search text`.
- Aliasing domain-specific commands (`periodic`, `obs`, `sync`, `backlinks`, `tags`). These have no clean filesystem equivalent.

## Motivation

LLMs are trained heavily on shell commands. `ls`, `cat`, `grep`, `find`, `tree` are deeply embedded in training data. An LLM can compose complex filesystem queries from these primitives with zero reasoning overhead. Blackglass-specific syntax (`notes get`, `search text`, `vault files`) requires the LLM to recall a custom API surface. Aliases close this gap.

Additionally, the Silt Framework requires a flat vault (no subdirectories). Enforcement at the API level prevents structural drift that convention alone cannot guarantee.

## Conventions

- All existing conventions from `2026-05-31-cli-full-coverage.md` apply.
- Aliases live at the top level of the CLI: `blackglass cat`, not `blackglass fs cat`.
- Aliases map to existing server endpoints. No new server routes for basic aliases.
- `head`, `tail`, and `tree` are new CLI-only commands that call existing endpoints with client-side post-processing.
- Flat enforcement applies to all write operations (create, move, update). Read operations strip directory prefixes defensively.

---

## Part 1: Flat Vault Enforcement

### Server-side (API)

**Rule:** All vault-relative paths must be root-level filenames. A path is valid if and only if it contains no `/` character other than the trailing `.md` extension separator.

**Validation logic:**

```python
def _validate_flat_path(path: str) -> str:
    """Reject paths with directory components."""
    # Strip .md extension for validation
    stem = path.removesuffix(".md")
    if "/" in stem or "\\" in stem:
        raise HTTPException(400, f"Flat vault enforced. Paths must be root-level: {path}")
    return path
```

**Affected endpoints (write operations):**

| Endpoint | Method | Behavior |
|---|---|---|
| `/vault/notes/{path}` | POST (create) | Reject if path contains `/` |
| `/vault/notes/{path}` | PUT (update) | Reject if path contains `/` |
| `/vault/notes/{path}` | DELETE | Reject if path contains `/` |
| `/vault/notes/{path}/move` | POST | Reject if destination contains `/` |
| `/vault/notes/{path}/patch` | PATCH | Reject if path contains `/` |
| `/vault/notes/{path}/set-frontmatter` | PATCH | Reject if path contains `/` |

**Read operations:** No rejection. Paths with `/` return 404 (file not found at root) or are stripped by the CLI (see below).

**Config toggle:** Add `flat` boolean to Blackglass config (default: `true`). When `false`, directory paths are allowed. When `true`, the validation above is enforced.

```yaml
# blackglass config
flat: true  # default; set false to allow subdirectories
```

### Client-side (CLI)

**Defensive stripping:** If a path argument contains `/`, the CLI strips everything before the last `/` and warns to stderr. This handles LLMs that accidentally write `blackglass cat "Folder/Note.md"`.

```bash
$ blackglass cat "Folder/Note.md"
WARN: Stripped directory prefix. Using 'Note.md' instead.
{ ... content of Note.md ... }
```

**Implementation:** Apply in the CLI's path-handling helper before forwarding to the API. No server changes needed for this behavior.

### Enforcement in Keepers

Keepers that create or move notes must use root-level paths. The Keeper template should include:

```python
path = path.lstrip("/")  # never absolute
if "/" in path.removesuffix(".md"):
    raise ValueError(f"Keeper attempted subdirectory path: {path}")
```

---

## Part 2: Filesystem Aliases

### Alias Table

| Alias | Maps to | New syntax | Notes |
|---|---|---|---|
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
| `cp` | `notes create` (copy content) | `blackglass cp <src> <dst>` | New command. Reads src, creates dst with same content. |
| `edit` | `notes replace` | `blackglass edit <path> --old "..." --new "..."` | Same behavior, shorter name |

### Commands that stay Blackglass-native

These commands have no clean filesystem equivalent and keep their current syntax:

| Command | Why no alias |
|---|---|
| `search semantic` | No filesystem equivalent for vector similarity |
| `search hybrid` | No filesystem equivalent for reciprocal rank fusion |
| `notes batch` | No filesystem equivalent for bulk reads |
| `notes set-frontmatter` | No filesystem equivalent for structured metadata |
| `notes append` / `notes prepend` | `tee -a` / `sed -i` are not clean analogs |
| `vault backlinks` | No filesystem equivalent |
| `vault tags` | No filesystem equivalent |
| `vault changes` | `git log` exists but different semantics |
| `vault sync` | No filesystem equivalent |
| `vault periodic` | Domain-specific |
| `obs *` | Domain-specific |

---

## Part 3: New Command Specifications

### `blackglass cat`

**Purpose:** Read a note's content. Direct analog to `cat`.

**Syntax:**
```bash
blackglass cat <path>
```

**Behavior:** Identical to `notes get`. Returns raw markdown content.

**Output:** Raw markdown to stdout.

**Example:**
```bash
$ blackglass cat "Silt Framework 2026-06-24.md"
# Silt Framework: Metadesign & Architectural Specification
...
```

### `blackglass head`

**Purpose:** Read the first N lines of a note. Direct analog to `head`.

**Syntax:**
```bash
blackglass head <path> [-n LINES]
```

**Params:**
- `path` (required, positional) — vault-relative path
- `-n` / `--lines` (optional, default: 10) — number of lines to return

**Implementation:** Calls `notes get`, splits on `\n`, takes first N lines, joins and prints.

**Output:** First N lines of the note to stdout.

**Example:**
```bash
$ blackglass head "Silt Framework 2026-06-24.md" -n 5
# Silt Framework: Metadesign & Architectural Specification

## I. System Mission & Core Philosophy

Silt is an automated cognitive pipeline designed to bridge unstructured Personal Knowledge Management
```

### `blackglass tail`

**Purpose:** Read the last N lines of a note. Direct analog to `tail`.

**Syntax:**
```bash
blackglass tail <path> [-n LINES]
```

**Params:**
- `path` (required, positional) — vault-relative path
- `-n` / `--lines` (optional, default: 10) — number of lines to return

**Implementation:** Calls `notes get`, splits on `\n`, takes last N lines, joins and prints.

**Output:** Last N lines of the note to stdout.

### `blackglass grep`

**Purpose:** Full-text search across all notes. Direct analog to `grep -r`.

**Syntax:**
```bash
blackglass grep "pattern" [--limit N]
```

**Params:**
- `query` (required, positional) — search pattern
- `--limit` (optional, default: 10) — max results

**Implementation:** Calls `search text` with the query. Returns results with path and snippet.

**Output:** JSON array of matches with path, excerpt, and score. Formatted for readability when `--pretty` is set.

**Example:**
```bash
$ blackglass grep "postgres indexing" --limit 5
[
  {
    "path": "Postgres Indexing Notes.md",
    "excerpt": "...strategies for GIN and GiST indexes...",
    "score": 0.89
  },
  ...
]
```

### `blackglass find`

**Purpose:** Find notes by filename pattern. Direct analog to `find -name`.

**Syntax:**
```bash
blackglass find <glob>
```

**Params:**
- `glob` (required, positional) — POSIX glob pattern

**Implementation:** Calls `vault files --path-glob <glob>`.

**Output:** JSON array of matching file paths.

**Example:**
```bash
$ blackglass find "Silt*"
["Silt Framework 2026-06-24.md", "Silt Framework - Primitive - Atomic Note.md", ...]
```

### `blackglass tree`

**Purpose:** Display vault structure as a tree. Direct analog to `tree`.

**Syntax:**
```bash
blackglass tree [--depth N]
```

**Params:**
- `--depth` (optional, default: 1) — tree depth (always 1 for flat vault, but parameter accepted for forward compatibility)

**Implementation:** Calls `vault files`, renders as indented tree. Since the vault is flat, this is always a single-level list with tree characters.

**Output:**
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

### `blackglass mv`

**Purpose:** Move or rename a note. Direct analog to `mv`.

**Syntax:**
```bash
blackglass mv <src> <dst>
```

**Behavior:** Identical to `notes move`. Rewrites wikilinks by default.

**Example:**
```bash
$ blackglass mv "Old Name.md" "New Name.md"
```

### `blackglass rm`

**Purpose:** Delete a note. Direct analog to `rm`.

**Syntax:**
```bash
blackglass rm <path>
```

**Behavior:** Identical to `notes delete`.

**Example:**
```bash
$ blackglass rm "Obsolete Note.md"
```

### `blackglass stat`

**Purpose:** Display note metadata. Direct analog to `stat`.

**Syntax:**
```bash
blackglass stat <path>
```

**Behavior:** Identical to `notes meta`. Returns size, mtime, frontmatter.

**Output:**
```json
{
  "path": "Silt Framework 2026-06-24.md",
  "exists": true,
  "size": 4521,
  "mtime": 1751132400.0,
  "frontmatter": {},
  "tags": [],
  "wikilinks_count": 7
}
```

### `blackglass touch`

**Purpose:** Create an empty note. Direct analog to `touch`.

**Syntax:**
```bash
blackglass touch <path>
```

**Implementation:** Calls `notes create` with empty content.

**Example:**
```bash
$ blackglass touch "Draft Note.md"
```

### `blackglass cp`

**Purpose:** Copy a note's content to a new note. Direct analog to `cp`.

**Syntax:**
```bash
blackglass cp <src> <dst>
```

**Implementation:** Calls `notes get` on src, then `notes create` on dst with the retrieved content.

**Example:**
```bash
$ blackglass cp "Template.md" "New Instance.md"
```

### `blackglass edit`

**Purpose:** Find-and-replace within a note. Direct analog to `sed -i`.

**Syntax:**
```bash
blackglass edit <path> --old "find" --new "replace" [--replace-all]
```

**Behavior:** Identical to `notes replace`.

**Example:**
```bash
$ blackglass edit "Config.md" --old "debug=true" --new "debug=false"
```

---

## Part 4: Path Handling

### Flat path enforcement (all commands)

Every command that accepts a `path` argument applies flat-path validation:

1. **Strip leading `/` and `~/` prefixes** — LLMs sometimes write absolute paths.
2. **Strip `.md` extension for validation** — check the stem for `/` or `\`.
3. **If stem contains `/`:**
   - Write operations: reject with 400.
   - Read operations (cat, head, tail, stat): strip directory prefix, warn to stderr, proceed with root-level filename.
4. **Re-append `.md`** if not present.

### Path normalization helper

```python
def normalize_flat_path(path: str) -> str:
    """Normalize a path to flat-vault conventions."""
    # Strip common prefixes
    path = path.lstrip("/")
    path = path.removeprefix("~/")

    # Strip .md for validation
    stem = path.removesuffix(".md")

    if "/" in stem or "\\" in stem:
        # Extract just the filename
        path = path.rsplit("/", 1)[-1]
        # Note: CLI should emit a warning here

    # Ensure .md extension
    if not path.endswith(".md"):
        path = path + ".md"

    return path
```

---

## Part 5: Implementation Plan

### Phase 1: Flat enforcement (server)

1. Add `flat` config option to Blackglass server config (default: `true`).
2. Add `_validate_flat_path()` helper to server route handlers.
3. Apply validation to all write endpoints (POST, PUT, DELETE, PATCH on `/vault/notes/{path}`).
4. Add tests for: valid root path, rejected subdirectory path, edge cases (`.md` in directory name, encoded slashes).

### Phase 2: CLI aliases (client)

1. Add `normalize_flat_path()` helper to CLI client.
2. Register alias commands in Click command group: `cat`, `ls`, `head`, `tail`, `grep`, `find`, `tree`, `mv`, `rm`, `stat`, `touch`, `cp`, `edit`.
3. Implement `head` and `tail` as CLI-only commands (call `notes get`, slice lines).
4. Implement `tree` as CLI-only command (call `vault files`, render tree).
5. Implement `cp` as CLI-only command (call `notes get` + `notes create`).
6. Add `--limit` flag to `grep` (maps to `search text` result count).
7. Add positional glob to `ls` and `find` (maps to `--path-glob`).
8. Add tests for all aliases, path normalization, and defensive stripping.

### Phase 3: Documentation

1. Update `SKILL.md` in the openclaw blackglass skill to document aliases.
2. Add alias reference to README.md.
3. Update the agentic extensions spec to reference flat enforcement.

---

## Acceptance Criteria

- [ ] `blackglass cat "Note.md"` returns note content (identical to `notes get`).
- [ ] `blackglass ls` lists all root-level notes.
- [ ] `blackglass grep "pattern"` returns text search results.
- [ ] `blackglass find "Silt*"` returns matching filenames.
- [ ] `blackglass tree` renders a flat tree.
- [ ] `blackglass head "Note.md" -n 5` returns first 5 lines.
- [ ] `blackglass tail "Note.md" -n 5` returns last 5 lines.
- [ ] `blackglass touch "New.md"` creates an empty note.
- [ ] `blackglass cp "A.md" "B.md"` copies content.
- [ ] `blackglass mv "A.md" "B.md"` renames with link rewriting.
- [ ] `blackglass rm "Note.md"` deletes the note.
- [ ] `blackglass stat "Note.md"` returns metadata.
- [ ] `blackglass edit "Note.md" --old "X" --new "Y"` replaces text.
- [ ] `blackglass cat "Folder/Note.md"` strips prefix, warns, reads `Note.md`.
- [ ] `blackglass notes create "Folder/Note.md" --content "..."` returns 400.
- [ ] All existing commands (`notes get`, `search text`, etc.) continue to work unchanged.
- [ ] `flat: false` config disables enforcement.

---

## Open Questions

1. **`grep` output format:** Should `grep` return raw JSON (like `search text`) or a more human-readable format (path + excerpt, no JSON envelope)? Recommendation: match `search text` output format for consistency; the LLM can parse JSON.

2. **`tree` depth in flat vault:** The `--depth` flag is accepted but always produces a single level. Should we document this as "always 1 for flat vaults" or just not expose the flag? Recommendation: accept but ignore; avoids breaking LLMs that pass `--depth 2` out of habit.

3. **`cp` with frontmatter:** Should `cp` copy frontmatter as well? Current `notes get` returns content including frontmatter. Recommendation: yes, copy everything; the user can modify frontmatter after.

4. **Alias conflicts:** If a future Blackglass command is named `cat` or `ls`, it would collide with aliases. Recommendation: namespace risk is low; filesystem commands are a closed set. Document the alias namespace as reserved.
