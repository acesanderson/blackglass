from __future__ import annotations
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def git_client(git_vault, monkeypatch):
    monkeypatch.setenv("BLACKGLASS_VAULT_PATH", str(git_vault))
    monkeypatch.setenv("BLACKGLASS_API_KEY", "test-key")
    monkeypatch.setenv("POSTGRES_PASSWORD", "ignored")
    import importlib
    # Import app first so all route modules are cached before we capture settings.
    from blackglass_server.main import app  # noqa: F401 — side-effect import
    from blackglass_server.routes import notes as _notes_mod
    live_settings = _notes_mod.settings
    from blackglass_server import config as cfg_mod
    importlib.reload(cfg_mod)
    monkeypatch.setattr(live_settings, "vault_path", git_vault)
    monkeypatch.setattr(live_settings, "api_key", "test-key")
    from blackglass_server import db as db_mod
    from blackglass_server import main as main_mod
    async def _no_pool(): return None
    monkeypatch.setattr(db_mod, "init_pool", _no_pool)
    monkeypatch.setattr(db_mod, "close_pool", _no_pool)
    monkeypatch.setattr(main_mod, "init_pool", _no_pool)
    monkeypatch.setattr(main_mod, "close_pool", _no_pool)
    return TestClient(app, headers={"X-API-Key": "test-key"})


def test_changes_recent(git_client):
    r = git_client.get("/vault/changes", params={"days": 30})
    assert r.status_code == 200
    body = r.json()
    paths = [c["path"] for c in body["changes"]]
    assert "alpha.md" in paths
    assert "epsilon.md" in paths
    assert any(c["change"] == "added" for c in body["changes"])


def test_changes_limit_one(git_client):
    r = git_client.get("/vault/changes", params={"days": 30, "limit": 1})
    body = r.json()
    assert len(body["changes"]) == 1
    assert body["truncated"] is True


def test_changes_days_zero_400(git_client):
    r = git_client.get("/vault/changes", params={"days": 0})
    assert r.status_code == 400


def test_changes_since_unparseable_400(git_client):
    r = git_client.get("/vault/changes", params={"since": "tomorrow"})
    assert r.status_code == 400


def test_changes_both_params_400(git_client):
    r = git_client.get("/vault/changes", params={"since": "1700000000", "days": 7})
    assert r.status_code == 400


def test_changes_not_a_repo_400(client):
    r = client.get("/vault/changes", params={"days": 7})
    assert r.status_code == 400


def test_changes_subprocess_timeout_504(git_client, monkeypatch):
    import subprocess
    def fake_git_changes(vault_path, since_epoch, include_diff_stats=False, timeout=10.0):
        raise subprocess.TimeoutExpired(cmd="git log", timeout=timeout)
    from blackglass_server.routes import vault_routes as vr
    monkeypatch.setattr(vr, "git_changes", fake_git_changes)
    r = git_client.get("/vault/changes", params={"days": 7})
    assert r.status_code == 504
    assert "timed out" in r.json()["detail"].lower()


def test_changes_include_diff_stats(git_client):
    r = git_client.get("/vault/changes", params={"days": 30, "include_diff_stats": "true"})
    assert r.status_code == 200
    body = r.json()
    # At least one change in git_vault has non-null diff_stats (the alpha.md modification)
    has_stats = [c for c in body["changes"] if c.get("diff_stats") is not None]
    assert len(has_stats) > 0
    s = has_stats[0]["diff_stats"]
    assert "added" in s and "removed" in s
    assert isinstance(s["added"], int)
    assert isinstance(s["removed"], int)


def test_changes_without_diff_stats_field_is_null(git_client):
    r = git_client.get("/vault/changes", params={"days": 30})
    assert r.status_code == 200
    body = r.json()
    # When include_diff_stats is false (default), every change has diff_stats: null
    for c in body["changes"]:
        assert c.get("diff_stats") is None
