from __future__ import annotations
import json
from blackglass_client.cli.main import cli


def test_vault_files_no_filters(runner, mock_api):
    route = mock_api.get("/vault/files").respond(200, json=["a.md", "b.md"])
    result = runner.invoke(cli, ["vault", "files"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == ["a.md", "b.md"]
    assert route.called
    assert str(route.calls.last.request.url) == "http://test-server/vault/files"


def test_vault_files_with_tags(runner, mock_api):
    mock_api.get("/vault/files").respond(200, json={"files": [], "total": 0, "filtered_from": 0})
    result = runner.invoke(
        cli, ["vault", "files", "--tag", "foo", "--tag", "bar", "--limit", "5"]
    )
    assert result.exit_code == 0
    qs = mock_api.calls.last.request.url.params
    assert qs.get_list("tag") == ["foo", "bar"]
    assert qs["limit"] == "5"


def test_vault_files_with_fm(runner, mock_api):
    mock_api.get("/vault/files").respond(200, json={"files": [], "total": 0, "filtered_from": 0})
    result = runner.invoke(
        cli, ["vault", "files", "--fm", "status=draft", "--fm", "type=note"]
    )
    assert result.exit_code == 0
    qs = mock_api.calls.last.request.url.params
    assert qs["fm.status"] == "draft"
    assert qs["fm.type"] == "note"


def test_vault_files_with_path_glob(runner, mock_api):
    mock_api.get("/vault/files").respond(200, json={"files": [], "total": 0, "filtered_from": 0})
    result = runner.invoke(cli, ["vault", "files", "--path-glob", "Daily/*.md"])
    assert result.exit_code == 0
    assert mock_api.calls.last.request.url.params["path_glob"] == "Daily/*.md"


def test_vault_files_bad_fm_format(runner, mock_api):
    result = runner.invoke(cli, ["vault", "files", "--fm", "no-equals-sign"])
    assert result.exit_code == 2


def test_vault_tags(runner, mock_api):
    route = mock_api.get("/vault/tags").respond(200, json=[{"tag": "blue", "count": 3}])
    result = runner.invoke(cli, ["vault", "tags"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == [{"tag": "blue", "count": 3}]


def test_vault_backlinks(runner, mock_api):
    route = mock_api.get("/vault/backlinks/foo.md").respond(
        200, json={"path": "foo.md", "backlinks": ["bar.md"]}
    )
    result = runner.invoke(cli, ["vault", "backlinks", "foo.md"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"path": "foo.md", "backlinks": ["bar.md"]}


def test_vault_sync(runner, mock_api):
    route = mock_api.post("/vault/sync").respond(
        200, json={"git": "ok", "files_checked": 100, "files_indexed": 4}
    )
    result = runner.invoke(cli, ["vault", "sync"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"git": "ok", "files_checked": 100, "files_indexed": 4}


def test_vault_changes_default(runner, mock_api):
    route = mock_api.get("/vault/changes").respond(200, json={"since": 0, "limit": 200, "changes": [], "truncated": False})
    result = runner.invoke(cli, ["vault", "changes"])
    assert result.exit_code == 0
    assert route.called
    assert dict(mock_api.calls.last.request.url.params) == {}


def test_vault_changes_with_days(runner, mock_api):
    mock_api.get("/vault/changes").respond(200, json={"since": 0, "limit": 10, "changes": [], "truncated": False})
    result = runner.invoke(cli, ["vault", "changes", "--days", "3", "--limit", "10", "--diff-stats"])
    assert result.exit_code == 0
    qs = mock_api.calls.last.request.url.params
    assert qs["days"] == "3"
    assert qs["limit"] == "10"
    assert qs["include_diff_stats"] == "true"


def test_vault_changes_with_since(runner, mock_api):
    mock_api.get("/vault/changes").respond(200, json={"since": 0, "limit": 200, "changes": [], "truncated": False})
    result = runner.invoke(cli, ["vault", "changes", "--since", "1700000000"])
    assert result.exit_code == 0
    assert mock_api.calls.last.request.url.params["since"] == "1700000000"
