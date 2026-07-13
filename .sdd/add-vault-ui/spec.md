# Spec: Add Vault Web UI

## Goal

Blackglass serves an Obsidian vault over an HTTP API designed for agent consumption, but has no human-facing interface. The primary gap is **mobile access** — reading notes from a phone without the Obsidian iOS app. This project builds a thin, read-only web frontend using Jinja2 + htmx mounted at `/ui` on the existing Blackglass server (port 8083), providing search, browse, and note-reading capabilities from any device on the VPN. The UI calls Blackglass's internal Python functions directly (no HTTP round-trip), requires zero JavaScript framework tooling, and ships as a single `routes/ui.py` router with templates and a CSS file.

## Interface / Scope

### In scope

- **Search** — hybrid search (text + semantic via RRF) with query highlighting in result excerpts
- **Browse by tag** — list all tags with note counts, filter notes by one or more tags (AND logic)
- **Browse all notes** — paginated file listing with sort options (alphabetical, recently modified, size)
- **Note reading** — rendered markdown with frontmatter metadata card, tag pills, wikilink resolution, syntax-highlighted code blocks, task lists, callouts, and backlinks
- **Recent changes** — 20 most recently changed notes from git history on the home page
- **Dark mode** — toggle persisted in `localStorage`, respects `prefers-color-scheme`, flash-free on load
- **Mobile-first responsive layout** — optimized for iPhone viewport (390×844), single-column, 720px max-width on desktop, 44×44px minimum touch targets

### Out of scope

- Write/edit operations (no create, update, delete, move, patch)
- Authentication UI (API key injected server-side; no login screen)
- User accounts (single-user, single API key)
- Offline/caching (no service worker, no local storage of note content)
- Obsidian plugin compatibility (standalone web app, not an Obsidian plugin)

### Mounting

The UI is mounted at `/ui` on the existing Blackglass server (port 8083). The API remains at its current endpoints unchanged. No new port, no new systemd service, no new process. Browser access: `http://172.16.0.3:8083/ui/`.

## Non-goals

1. **Not a replacement for Obsidian.** This is a lightweight reading companion, not a full-featured note editor.
2. **No offline support.** VPN access is assumed; no service workers or local caching.
3. **No collaborative features.** Single-user design with no multi-tenancy, sharing, or permissions.
4. **No external-facing security.** VPN provides the security boundary; no TLS, no rate limiting, no CORS in v1.

## Design decisions

### 1. Internal function calls over HTTP proxy

The UI router imports and calls `vault.read_note()`, `vault.fulltext_search()`, `vault.list_files_filtered()`, etc. directly — same process, same vault, same auth context. No self-referential HTTP calls.

**Trade-off chosen:** Direct function calls. Zero latency overhead, no need to pass API key internally, simpler error handling. The API endpoints remain unchanged and available for external consumers.

**Alternative rejected:** HTTP proxy to own API. Would add latency, require API key forwarding, and create a circular dependency for no benefit since the UI lives in the same process.

### 2. htmx over React/Vue/Svelte

htmx handles partial page updates (search results loading, note content swapping) via HTML attributes on server-rendered fragments.

**Trade-off chosen:** htmx (~14KB gzipped). Zero build step — no npm, no bundler, no `node_modules`. Server-rendered HTML gives fast first paint and works without JS (progressive enhancement). Aligns with Blackglass's Python-only stack.

**Alternative rejected:** React/Vue/Svelte SPA. Would require a Node.js build pipeline, client-side routing, JSON-to-HTML conversion in the browser, and state management — massive complexity for a read-only viewer.

### 3. mistune for markdown rendering

mistune is fast, supports plugins, and handles the subset of Obsidian markdown we need (wikilinks, task lists, frontmatter, callouts).

**Trade-off chosen:** mistune 3.x. Faster than markdown-it-py for our use case, plugin architecture for wikilinks and task lists, Pygments integration for code highlighting, single dependency with no native compilation.

**Alternative rejected:** markdown-it-py. Slower, more complex API, and we don't need the extra flexibility.

### 4. Server-side rendering only

All HTML is generated server-side. htmx swaps HTML fragments for partial updates. No client-side templating, no JSON-to-HTML conversion in the browser.

**Trade-off chosen:** Full server-side rendering. Zero client-side state management, works without JavaScript (full page navigation still works as plain HTML links), simpler security model (no XSS from client-side rendering), mobile browsers handle server-rendered HTML efficiently.

**Alternative rejected:** Client-side rendering with JSON API. Would require a JSON serialization layer, client-side template engine, XSS mitigation for dynamic HTML injection, and more complex debugging.

## Changes

### Directory structure

```
blackglass-server/
├── src/blackglass_server/
│   ├── routes/
│   │   ├── ui.py              # NEW — UI routes (/ui/*)
│   │   ├── notes.py           # existing (unchanged)
│   │   ├── search.py          # existing (unchanged)
│   │   └── vault_routes.py    # existing (unchanged)
│   ├── templates/             # NEW — Jinja2 templates
│   │   ├── base.html
│   │   ├── home.html
│   │   ├── search.html
│   │   ├── browse.html
│   │   ├── note.html
│   │   └── partials/
│   │       ├── search_results.html
│   │       ├── note_list.html
│   │       └── nav.html
│   ├── static/                # NEW — static assets
│   │   ├── css/
│   │   │   └── vault.css
│   │   ├── js/
│   │   │   └── dark-mode.js
│   │   └── htmx.min.js
│   └── markdown.py            # NEW — Obsidian-flavored markdown renderer
```

### Route table

| Route | Method | Description |
|---|---|---|
| `/ui/` | GET | Home page — search bar + recent changes |
| `/ui/search?q=...` | GET | Search results (full page) |
| `/ui/search/results?q=...` | GET | Search results partial (htmx swap target) |
| `/ui/browse` | GET | Browse all notes (paginated, 50/page) |
| `/ui/browse?tag=...` | GET | Browse filtered by tag |
| `/ui/browse/tags` | GET | Tag list view with counts |
| `/ui/note/{path:path}` | GET | Note reading view |
| `/ui/note/{path:path}/backlinks` | GET | Backlinks partial (htmx) |

All routes return HTML. No JSON API additions.

### CSS architecture

Single `vault.css` file using CSS custom properties for theming:

```css
:root {
  --bg: #FAFAFA;
  --surface: #FFFFFF;
  --text: #1a1a1a;
  --text-secondary: #666;
  --accent: #6366F1;
}

[data-theme="dark"] {
  --bg: #1a1a1a;
  --surface: #2a2a2a;
  --text: #e5e5e5;
  --text-secondary: #999;
}
```

Dark mode toggle sets `data-theme` on `<html>` and persists to `localStorage`. An inline `<script>` in `<head>` (before body render) reads the stored preference to prevent flash of wrong theme.

### Wikilink resolution

Wikilinks (`[[Note Name]]` or `[[Note Name|display text]]`) are resolved at render time:

1. Extract the target stem from the wikilink
2. Look up the note by stem in the vault (via `vault.list_files()`)
3. If found: render as `<a href="/ui/note/{path}">display text</a>`
4. If not found: render as `<span class="broken-link">display text</span>`

Resolution is not cached. The vault (~1000 notes) is small enough that the file listing can be loaded once per request and reused for all wikilinks in a single note.

### Pagination strategy

Browse view paginates at 50 notes per page. Uses htmx infinite scroll pattern:

- Initial page loads first 50 results
- Scroll-to-bottom triggers htmx request for next page
- Results append to the list
- URL updates via `hx-push-url`

### Dependencies

| Package | Version | Purpose | New? |
|---|---|---|---|
| `fastapi` | existing | Routing | No |
| `jinja2` | latest | Templating | Yes |
| `mistune` | 3.x | Markdown rendering | Yes |
| `pygments` | existing (transitive) | Code highlighting | No |
| `htmx.org` | 2.0 | Partial page updates | Yes (static file) |

No new database tables. No new API endpoints. The frontend consumes existing Blackglass internals.

### Mockups

SVG mockups for the three main views:

- [Home view](openspec/changes/add-vault-ui/mockups/vault-ui-mockup-1-home.svg) — search bar + recent notes with tag pills
- [Search results](openspec/changes/add-vault-ui/mockups/vault-ui-mockup-2-search.svg) — ranked results with excerpts, scores, query highlighting
- [Note view](openspec/changes/add-vault-ui/mockups/vault-ui-mockup-3-note.svg) — rendered markdown with frontmatter tags and backlinks

## Acceptance criteria

1. Navigating to `http://<host>:8083/ui/` loads the home page with a search bar and recent changes section within 2 seconds on a 3G connection.
2. Typing a query and submitting displays hybrid search results ranked by RRF score, with the note title, a snippet with query terms highlighted in `<mark>` tags, and the search score.
3. Submitting an empty search does not perform a search and displays the home page unchanged.
4. A search returning zero results shows "No results found for '{query}'" and retains the query in the search bar.
5. When semantic search is unavailable, a "text-only" indicator appears next to the result count.
6. Clicking a note from search results or browse loads the note view with frontmatter tags as colored pills, the `created` date, and the markdown body rendered as HTML.
7. Wikilinks (`[[Note Name]]`) in rendered notes are clickable and navigate to `/ui/note/{path}`. Broken wikilinks display as plain text with a subtle visual indicator (e.g., strikethrough or muted color).
8. Fenced code blocks with a language identifier render with Pygments syntax highlighting and display the language label.
9. Task list items (`- [ ]` / `- [x]`) render as read-only checked/unchecked indicators.
10. External links (`[text](url)`) open in a new tab with `rel="noopener"`.
11. Navigating to a nonexistent note shows a "Note not found" message with a link back to the home page.
12. The browse view lists all tags with note counts, sorted by count descending. Selecting a tag filters notes to those matching that tag in frontmatter. Selecting a second tag applies AND logic. Each selected tag has an individual remove button and there is a clear-all option.
13. Browse shows notes paginated at 50 per page with sort options: alphabetical (default), recently modified, and size.
14. The backlinks section below a note's content shows clickable links to all notes that wikilink to it. When no backlinks exist, the section is hidden.
15. The dark mode toggle switches between light and dark color schemes, persists the preference in `localStorage`, respects `prefers-color-scheme` on first visit, and does not flash the wrong theme on load.
16. The layout is single-column on mobile (390×844 viewport) with touch targets at least 44×44px and minimum 14px body text. On desktop, content is centered with a 720px max-width.
17. A bottom navigation bar with Search and Browse icons is visible on every page, with the active view's icon highlighted.
18. The back button returns from a note to the search results with the original query preserved in history (via `hx-push-url`).
19. The total client-side JavaScript payload is ≤ 20KB gzipped (htmx + dark mode script).
20. All routes return HTTP 200 on success and HTTP 404 on missing resources. The existing API at `/vault/*` remains unchanged.