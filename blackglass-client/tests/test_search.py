from __future__ import annotations
import json
from blackglass_client.cli.main import cli


def test_search_text(runner, mock_api):
    route = mock_api.get("/vault/search").respond(200, json=[{"path": "a.md", "score": 1.0}])
    result = runner.invoke(cli, ["search", "text", "hello"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == [{"path": "a.md", "score": 1.0}]
    qs = mock_api.calls.last.request.url.params
    assert qs["q"] == "hello"
    assert "snippet_chars" not in qs


def test_search_text_snippet_chars(runner, mock_api):
    mock_api.get("/vault/search").respond(200, json=[])
    result = runner.invoke(cli, ["search", "text", "hello", "--snippet-chars", "500"])
    assert result.exit_code == 0
    assert mock_api.calls.last.request.url.params["snippet_chars"] == "500"


def test_search_semantic(runner, mock_api):
    route = mock_api.get("/vault/semantic-search").respond(200, json=[{"path": "a.md"}])
    result = runner.invoke(cli, ["search", "semantic", "vector query"])
    assert result.exit_code == 0
    assert mock_api.calls.last.request.url.params["q"] == "vector query"


def test_search_semantic_limit(runner, mock_api):
    mock_api.get("/vault/semantic-search").respond(200, json=[])
    result = runner.invoke(
        cli, ["search", "semantic", "x", "--limit", "5", "--snippet-chars", "200"]
    )
    assert result.exit_code == 0
    qs = mock_api.calls.last.request.url.params
    assert qs["limit"] == "5"
    assert qs["snippet_chars"] == "200"


def test_search_hybrid(runner, mock_api):
    route = mock_api.get("/vault/hybrid-search").respond(
        200, json={"results": [{"path": "a.md", "score": 0.5}], "degraded": None}
    )
    result = runner.invoke(cli, ["search", "hybrid", "x"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"results": [{"path": "a.md", "score": 0.5}], "degraded": None}


def test_search_hybrid_all_params(runner, mock_api):
    mock_api.get("/vault/hybrid-search").respond(
        200, json={"results": [], "degraded": None}
    )
    result = runner.invoke(
        cli,
        ["search", "hybrid", "x", "--limit", "20", "--snippet-chars", "0", "--k", "30"],
    )
    assert result.exit_code == 0
    qs = mock_api.calls.last.request.url.params
    assert qs["limit"] == "20"
    assert qs["snippet_chars"] == "0"
    assert qs["k"] == "30"
