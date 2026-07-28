from __future__ import annotations
from blackglass_client.cli.publish import strip_frontmatter, get_note_date


class TestStripFrontmatter:
    def test_strips_frontmatter(self):
        content = "---\ntags: [foo]\ndate: 2026-07-28\n---\n\n# Title\nBody"
        assert strip_frontmatter(content) == "# Title\nBody"

    def test_no_frontmatter(self):
        content = "# Title\nBody"
        assert strip_frontmatter(content) == "# Title\nBody"

    def test_empty_frontmatter(self):
        content = "---\n---\n\n# Title"
        assert strip_frontmatter(content) == "# Title"

    def test_frontmatter_with_dashes_in_body(self):
        content = "---\ntags: [foo]\n---\n\n# Title\n---\nMore content"
        result = strip_frontmatter(content)
        assert result == "# Title\n---\nMore content"


class TestGetNoteDate:
    def test_extracts_date(self):
        content = "---\ndate: 2026-07-28\ntags: [foo]\n---\nBody"
        assert get_note_date(content) == "2026-07-28"

    def test_no_date_returns_today(self):
        content = "---\ntags: [foo]\n---\nBody"
        result = get_note_date(content)
        # Should be today's date in YYYY-MM-DD format
        assert len(result) == 10
        assert result.count("-") == 2

    def test_no_frontmatter_returns_today(self):
        content = "# Title\nBody"
        result = get_note_date(content)
        assert len(result) == 10
