from __future__ import annotations
import json
import sys
import httpx
import pytest
import respx
from blackglass_client.client import request


def test_request_success_returns_json(mock_api):
    mock_api.get("/vault/notes/foo.md").respond(200, json={"path": "foo.md", "content": "x"})
    result = request("GET", "/vault/notes/foo.md")
    assert result == {"path": "foo.md", "content": "x"}


def test_request_204_returns_none(mock_api):
    mock_api.delete("/vault/notes/foo.md").respond(204)
    result = request("DELETE", "/vault/notes/foo.md")
    assert result is None


def test_request_4xx_emits_envelope_and_exits_4(mock_api, capsys):
    mock_api.get("/vault/notes/missing.md").respond(404, json={"detail": "Note not found: missing.md"})
    with pytest.raises(SystemExit) as exc:
        request("GET", "/vault/notes/missing.md")
    assert exc.value.code == 4
    captured = capsys.readouterr()
    assert captured.out == ""
    envelope = json.loads(captured.err)
    assert envelope == {
        "error": "http_error",
        "status": 404,
        "method": "GET",
        "path": "/vault/notes/missing.md",
        "detail": "Note not found: missing.md",
    }


def test_request_5xx_exits_5(mock_api, capsys):
    mock_api.get("/vault/files").respond(500, json={"detail": "boom"})
    with pytest.raises(SystemExit) as exc:
        request("GET", "/vault/files")
    assert exc.value.code == 5
    envelope = json.loads(capsys.readouterr().err)
    assert envelope["error"] == "http_error"
    assert envelope["status"] == 500


def test_request_4xx_structured_detail_passthrough(mock_api, capsys):
    mock_api.patch("/vault/notes/x.md").respond(
        409,
        json={"detail": {"message": "old matched multiple times", "match_count": 3}},
    )
    with pytest.raises(SystemExit):
        request("PATCH", "/vault/notes/x.md", json={"op": "replace"})
    envelope = json.loads(capsys.readouterr().err)
    assert envelope["detail"] == {"message": "old matched multiple times", "match_count": 3}


def test_request_4xx_non_json_body(mock_api, capsys):
    mock_api.get("/vault/files").respond(400, content="not json", headers={"content-type": "text/plain"})
    with pytest.raises(SystemExit):
        request("GET", "/vault/files")
    envelope = json.loads(capsys.readouterr().err)
    assert envelope["detail"] == "not json"


def test_request_transport_error_exits_1(monkeypatch, capsys):
    def boom(*a, **kw):
        raise httpx.ConnectError("connection refused")
    monkeypatch.setattr(httpx.Client, "request", boom)
    with pytest.raises(SystemExit) as exc:
        request("GET", "/vault/files")
    assert exc.value.code == 1
    envelope = json.loads(capsys.readouterr().err)
    assert envelope["error"] == "transport_error"
    assert envelope["status"] is None
    assert "ConnectError" in envelope["detail"]
