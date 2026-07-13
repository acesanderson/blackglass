# Plan: Add Vault UI

- [ ] 1. Add `jinja2` and `mistune` to `pyproject.toml`, create `templates/`, `static/` directory structures, download `htmx.min.js`, configure Jinja2 template loader in FastAPI app
- [ ] 2. Create `markdown.py` with mistune-based renderer: wikilink plugin (`[[Note Name]]` and `[[Note Name|display text]]`), broken wikilink detection, task list rendering, Pygments code block integration, callout/admonition rendering, and unit tests
- [ ] 3. Create `base.html` template with HTML shell, meta viewport, htmx script tag, CSS link, inline flash-free theme script in `<head>`, and bottom navigation bar partial
- [ ] 4. Create `vault.css` with CSS custom properties for light theme, dark theme variables (`[data-theme="dark"]`), responsive layout (single-column, 720px max-width on desktop, 44×44px touch targets), card and tag pill component styles
- [ ] 5. Create `dark-mode.js` with localStorage persistence, `prefers-color-scheme` detection, and toggle button wiring
- [ ] 6. Create `routes/ui.py` with FastAPI router mounted at `/ui`, wire into `main.py`, implement template dependency injection (vault path, tag data)
- [ ] 7. Mount static files directory in FastAPI at `/ui/static`, set cache headers, verify static paths work from `/ui/` prefix
- [ ] 8. Implement home page route (`GET /ui/`) with `home.html` template: search bar, recent changes from git history (gracefully hide when vault is not a git repo), styled recent note cards with title, excerpt, tags, date
- [ ] 9. Implement search routes (`GET /ui/search`, `GET /ui/search/results`): create `search.html` and `partials/search_results.html` templates, call `hybrid_search()` internally, query term highlighting in excerpts, empty query handling, no-results state, degraded search indicator, htmx form submission for partial swap
- [ ] 10. Implement browse routes (`GET /ui/browse`, `GET /ui/browse?tag=...`, `GET /ui/browse/tags`): create `browse.html` and `partials/note_list.html` templates, tag list with counts sorted descending, note listing with pagination (50/page), tag filtering (single and multiple with AND logic), active tag filter display with remove buttons and clear-all
- [ ] 11. Implement sort options in browse view: alphabetical (default), recently modified, size
- [ ] 12. Implement htmx infinite scroll pagination for browse (50 per page, append on scroll, `hx-push-url` for URL updates)
- [ ] 13. Implement note view route (`GET /ui/note/{path:path}`): create `note.html` template, read note and render markdown via the markdown renderer, frontmatter tags as colored pills, frontmatter `created` date in metadata card, external links with `target="_blank" rel="noopener"`
- [ ] 14. Implement backlinks: call `vault.compute_backlinks()` internally, render backlinks section below note content, hide section when no backlinks exist, implement backlinks partial route (`GET /ui/note/{path:path}/backlinks`)
- [ ] 15. Implement note-not-found state (404 page with link to home)
- [ ] 16. Implement navigation: back button returns from note to search results with query preserved (htmx `hx-push-url`), bottom nav highlights active view
- [ ] 17. Write integration tests for all routes (200 on success, 404 on not found), search returns expected structure, note renders with frontmatter and markdown, browse pagination works, tag filtering works, backlinks appear when expected
- [ ] 18. Manual visual testing: iPhone viewport (390×844), dark mode toggle, htmx interactions (search, navigation), desktop layout