from __future__ import annotations
import json
from blackglass_client.cli.main import cli


def test_obs_status(runner, mock_api):
    route = mock_api.get("/status").respond(200, json={"name": "blackglass", "version": "0.1.0"})
    result = runner.invoke(cli, ["obs", "status"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {"name": "blackglass", "version": "0.1.0"}


def test_obs_logs_last_default(runner, mock_api):
    route = mock_api.get("/logs/last").respond(200, json={"entries": [], "total_buffered": 0, "capacity": 1000})
    result = runner.invoke(cli, ["obs", "logs-last"])
    assert result.exit_code == 0
    assert dict(mock_api.calls.last.request.url.params) == {}


def test_obs_logs_last_with_n(runner, mock_api):
    mock_api.get("/logs/last").respond(200, json={"entries": [], "total_buffered": 0, "capacity": 1000})
    result = runner.invoke(cli, ["obs", "logs-last", "-n", "25"])
    assert result.exit_code == 0
    assert mock_api.calls.last.request.url.params["n"] == "25"


def test_obs_logs_journal_default(runner, mock_api):
    route = mock_api.get("/logs/journal").respond(200, json={"unit": "blackglass", "n_requested": 100, "lines": []})
    result = runner.invoke(cli, ["obs", "logs-journal"])
    assert result.exit_code == 0


def test_obs_logs_journal_with_n(runner, mock_api):
    mock_api.get("/logs/journal").respond(200, json={"unit": "blackglass", "n_requested": 200, "lines": []})
    result = runner.invoke(cli, ["obs", "logs-journal", "-n", "200"])
    assert result.exit_code == 0
    assert mock_api.calls.last.request.url.params["n"] == "200"
