from __future__ import annotations
import json
import httpx
from blackglass_client.cli.main import cli


def _ok(mock_api, method: str, path: str, body):
    return getattr(mock_api, method.lower())(path).respond(200, json=body)


def test_notes_get(runner, mock_api):
    route = mock_api.get("/vault/notes/foo.md").respond(200, json={"path": "foo.md", "content": "hi"})
    result = runner.invoke(cli, ["notes", "get", "foo.md"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {"path": "foo.md", "content": "hi"}
    assert route.called


def test_notes_meta(runner, mock_api):
    route = mock_api.get("/vault/notes/foo.md/meta").respond(200, json={"path": "foo.md", "size": 10})
    result = runner.invoke(cli, ["notes", "meta", "foo.md"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"path": "foo.md", "size": 10}
    assert route.called


def test_notes_create(runner, mock_api):
    route = mock_api.post("/vault/notes").respond(201, json={"path": "new.md", "content": "x"})
    result = runner.invoke(cli, ["notes", "create", "new.md", "--content", "x"])
    assert result.exit_code == 0
    assert route.called
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"content": "x"}
    assert route.calls.last.request.url.params["path"] == "new.md"


def test_notes_update(runner, mock_api):
    route = mock_api.put("/vault/notes/foo.md").respond(200, json={"path": "foo.md", "content": "new"})
    result = runner.invoke(cli, ["notes", "update", "foo.md", "--content", "new"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"content": "new"}


def test_notes_append(runner, mock_api):
    route = mock_api.patch("/vault/notes/foo.md").respond(200, json={"path": "foo.md", "content": "a\nb"})
    result = runner.invoke(cli, ["notes", "append", "foo.md", "b"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"op": "append", "content": "b"}


def test_notes_prepend(runner, mock_api):
    route = mock_api.patch("/vault/notes/foo.md").respond(200, json={"path": "foo.md"})
    result = runner.invoke(cli, ["notes", "prepend", "foo.md", "intro"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"op": "prepend", "content": "intro"}


def test_notes_set_frontmatter(runner, mock_api):
    route = mock_api.patch("/vault/notes/foo.md").respond(200, json={"path": "foo.md"})
    result = runner.invoke(cli, ["notes", "set-frontmatter", "foo.md", "tag", "blue"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {
        "op": "set_frontmatter",
        "key": "tag",
        "value": "blue",
    }


def test_notes_replace(runner, mock_api):
    route = mock_api.patch("/vault/notes/foo.md").respond(200, json={"path": "foo.md"})
    result = runner.invoke(cli, ["notes", "replace", "foo.md", "--old", "x", "--new", "y"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {
        "op": "replace",
        "old": "x",
        "new": "y",
        "replace_all": False,
    }


def test_notes_replace_all(runner, mock_api):
    route = mock_api.patch("/vault/notes/foo.md").respond(200, json={"path": "foo.md"})
    result = runner.invoke(
        cli, ["notes", "replace", "foo.md", "--old", "x", "--new", "y", "--replace-all"]
    )
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content)["replace_all"] is True


def test_notes_delete(runner, mock_api):
    route = mock_api.delete("/vault/notes/foo.md").respond(204)
    result = runner.invoke(cli, ["notes", "delete", "foo.md"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert route.called


def test_notes_batch_positional(runner, mock_api):
    route = mock_api.post("/vault/notes/batch").respond(200, json={"results": [], "summary": {}})
    result = runner.invoke(cli, ["notes", "batch", "a.md", "b.md"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"paths": ["a.md", "b.md"]}


def test_notes_batch_stdin(runner, mock_api):
    route = mock_api.post("/vault/notes/batch").respond(200, json={"results": [], "summary": {}})
    result = runner.invoke(cli, ["notes", "batch", "--stdin"], input="a.md\nb.md\n")
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"paths": ["a.md", "b.md"]}


def test_notes_batch_both_is_usage_error(runner, mock_api):
    result = runner.invoke(cli, ["notes", "batch", "--stdin", "a.md"])
    assert result.exit_code == 2


def test_notes_move(runner, mock_api):
    route = mock_api.post("/vault/notes/old.md/move").respond(200, json={"from": "old.md", "to": "new.md"})
    result = runner.invoke(cli, ["notes", "move", "old.md", "new.md"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"to": "new.md", "rewrite_links": True}


def test_notes_move_no_rewrite(runner, mock_api):
    route = mock_api.post("/vault/notes/old.md/move").respond(200, json={"from": "old.md", "to": "new.md"})
    result = runner.invoke(cli, ["notes", "move", "old.md", "new.md", "--no-rewrite-links"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"to": "new.md", "rewrite_links": False}


def test_pretty_flag(runner, mock_api):
    mock_api.get("/vault/notes/foo.md").respond(200, json={"a": 1})
    result = runner.invoke(cli, ["--pretty", "notes", "get", "foo.md"])
    assert result.exit_code == 0
    assert result.stdout == '{\n  "a": 1\n}\n'
