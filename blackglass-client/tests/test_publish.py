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


import respx


class TestCreateGist:
    def test_creates_public_gist(self, monkeypatch):
        monkeypatch.setenv("GITHUB_PERSONAL_TOKEN", "ghp_test123")
        gist_response = {
            "url": "https://api.github.com/gists/abc123",
            "html_url": "https://gist.github.com/user/abc123",
            "id": "abc123",
            "public": True,
            "files": {"test.md": {"filename": "test.md"}},
        }
        with respx.mock(base_url="https://api.github.com") as github:
            route = github.post("/gists").respond(201, json=gist_response)
            from blackglass_client.cli.publish import create_gist
            result = create_gist("ghp_test123", "test.md", "# Content", "Test gist", True)
            assert result["id"] == "abc123"
            assert result["html_url"] == "https://gist.github.com/user/abc123"
            assert route.called
            sent = route.calls.last.request.content
            assert b'"public":true' in sent
            assert b'"# Content"' in sent

    def test_creates_private_gist(self, monkeypatch):
        monkeypatch.setenv("GITHUB_PERSONAL_TOKEN", "ghp_test123")
        gist_response = {
            "url": "https://api.github.com/gists/def456",
            "html_url": "https://gist.github.com/user/def456",
            "id": "def456",
            "public": False,
            "files": {"test.md": {"filename": "test.md"}},
        }
        with respx.mock(base_url="https://api.github.com") as github:
            route = github.post("/gists").respond(201, json=gist_response)
            from blackglass_client.cli.publish import create_gist
            result = create_gist("ghp_test123", "test.md", "# Content", "Test gist", False)
            assert result["public"] is False
            sent = route.calls.last.request.content
            assert b'"public":false' in sent


from click.testing import CliRunner
from blackglass_client.cli.main import cli


class TestPublishCommand:
    def test_publish_happy_path(self, runner, mock_api, monkeypatch):
        monkeypatch.setenv("GITHUB_PERSONAL_TOKEN", "ghp_test123")
        note_content = "---\ntags: [foo]\ndate: 2026-07-28\n---\n\n# My Note\nBody text"
        mock_api.get("/vault/notes/My%20Note.md").respond(
            200, json={"path": "My Note.md", "content": note_content}
        )
        gist_response = {
            "url": "https://api.github.com/gists/abc123",
            "html_url": "https://gist.github.com/user/abc123",
            "id": "abc123",
            "public": True,
            "files": {"My Note.md": {"filename": "My Note.md"}},
        }
        with respx.mock(base_url="https://api.github.com") as github:
            github.post("/gists").respond(201, json=gist_response)
            result = runner.invoke(cli, ["publish", "My Note.md"])
            assert result.exit_code == 0, result.stderr
            import json
            data = json.loads(result.stdout)
            assert data["html_url"] == "https://gist.github.com/user/abc123"
            assert data["id"] == "abc123"
            assert data["filename"] == "My Note.md"
            assert data["public"] is True

    def test_publish_private_flag(self, runner, mock_api, monkeypatch):
        monkeypatch.setenv("GITHUB_PERSONAL_TOKEN", "ghp_test123")
        mock_api.get("/vault/notes/foo.md").respond(
            200, json={"path": "foo.md", "content": "---\ndate: 2026-01-01\n---\nBody"}
        )
        gist_response = {
            "url": "https://api.github.com/gists/priv123",
            "html_url": "https://gist.github.com/user/priv123",
            "id": "priv123",
            "public": False,
            "files": {"foo.md": {"filename": "foo.md"}},
        }
        with respx.mock(base_url="https://api.github.com") as github:
            github.post("/gists").respond(201, json=gist_response)
            result = runner.invoke(cli, ["publish", "foo.md", "--private"])
            assert result.exit_code == 0, result.stderr
            import json
            data = json.loads(result.stdout)
            assert data["public"] is False

    def test_publish_missing_token(self, runner, mock_api, monkeypatch):
        monkeypatch.delenv("GITHUB_PERSONAL_TOKEN", raising=False)
        result = runner.invoke(cli, ["publish", "foo.md"])
        assert result.exit_code == 1
        assert "GITHUB_PERSONAL_TOKEN" in result.stderr

    def test_publish_note_not_found(self, runner, mock_api, monkeypatch):
        monkeypatch.setenv("GITHUB_PERSONAL_TOKEN", "ghp_test123")
        mock_api.get("/vault/notes/missing.md").respond(404, json={"detail": "Not found"})
        result = runner.invoke(cli, ["publish", "missing.md"])
        assert result.exit_code == 4
