from __future__ import annotations
import json
from blackglass_client.cli.main import cli


def test_periodic_list(runner, mock_api):
    route = mock_api.get("/vault/periodic").respond(200, json=[{"path": "2026-05-30.md"}])
    result = runner.invoke(cli, ["vault", "periodic", "list"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == [{"path": "2026-05-30.md"}]
    assert route.called


def test_periodic_today(runner, mock_api):
    route = mock_api.get("/vault/periodic/today").respond(200, json={"path": "today.md", "created": True})
    result = runner.invoke(cli, ["vault", "periodic", "today"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"path": "today.md", "created": True}


def test_periodic_yesterday(runner, mock_api):
    route = mock_api.get("/vault/periodic/yesterday").respond(200, json={"path": "yesterday.md", "created": False})
    result = runner.invoke(cli, ["vault", "periodic", "yesterday"])
    assert result.exit_code == 0
    assert route.called


def test_periodic_on(runner, mock_api):
    route = mock_api.get("/vault/periodic/by-date/2026-05-31").respond(200, json={"path": "2026-05-31.md", "created": False})
    result = runner.invoke(cli, ["vault", "periodic", "on", "2026-05-31"])
    assert result.exit_code == 0
    assert route.called


def test_periodic_append_today(runner, mock_api):
    route = mock_api.post("/vault/periodic/today/append").respond(200, json={"path": "today.md"})
    result = runner.invoke(cli, ["vault", "periodic", "append-today", "more stuff"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"content": "more stuff"}


def test_periodic_patch_today_append(runner, mock_api):
    route = mock_api.patch("/vault/periodic/today").respond(200, json={"path": "today.md"})
    result = runner.invoke(cli, ["vault", "periodic", "patch-today", "append", "hello"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"op": "append", "content": "hello"}


def test_periodic_patch_today_prepend(runner, mock_api):
    route = mock_api.patch("/vault/periodic/today").respond(200, json={"path": "today.md"})
    result = runner.invoke(cli, ["vault", "periodic", "patch-today", "prepend", "hi"])
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"op": "prepend", "content": "hi"}


def test_periodic_patch_today_set_frontmatter(runner, mock_api):
    route = mock_api.patch("/vault/periodic/today").respond(200, json={"path": "today.md"})
    result = runner.invoke(
        cli, ["vault", "periodic", "patch-today", "set-frontmatter", "mood", "great"]
    )
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {
        "op": "set_frontmatter",
        "key": "mood",
        "value": "great",
    }


def test_periodic_patch_today_replace(runner, mock_api):
    route = mock_api.patch("/vault/periodic/today").respond(200, json={"path": "today.md"})
    result = runner.invoke(
        cli, ["vault", "periodic", "patch-today", "replace", "--old", "x", "--new", "y"]
    )
    assert result.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {
        "op": "replace",
        "old": "x",
        "new": "y",
        "replace_all": False,
    }
