from __future__ import annotations
import importlib
import os
import subprocess
import textwrap
import pytest
from pathlib import Path
from fastapi.testclient import TestClient


# Fixture name `vault` is used by all Task 1-9 tests in this plan; intentionally
# shadowed by test_vault.py's older local fixture (pytest local-fixture precedence).
# textwrap.dedent calls below keep a trailing newline on the last line, matching
# how Obsidian writes notes; assertions on exact content length should account for it.
@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Vault with a known mix of notes, frontmatter, tags, subdirs, skip dirs."""
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".trash").mkdir()
    (tmp_path / "Work Docs" / "Sub").mkdir(parents=True)
    (tmp_path / "Daily").mkdir()

    (tmp_path / "alpha.md").write_text("AAA BBB CCC " * 20)
    (tmp_path / "beta.md").write_text(textwrap.dedent("""\
        ---
        status: in-progress
        tags: [foo]
        ---
        Beta body referencing [[alpha]].
    """))
    (tmp_path / "gamma.md").write_text(textwrap.dedent("""\
        ---
        status: done
        tags: [foo, bar]
        priority: 3
        ---
        Gamma body.
    """))
    (tmp_path / "delta.md").write_text(textwrap.dedent("""\
        ---
        archived: true
        ---
        Delta body with [[alpha|the first one]] alias link.
    """))
    (tmp_path / "Work Docs" / "foo.md").write_text("Work doc foo.")
    (tmp_path / "Work Docs" / "Sub" / "bar.md").write_text("Nested work doc bar.")
    (tmp_path / "Daily" / "2026-05-29.md").write_text("Yesterday.")
    (tmp_path / "2026-05-30.md").write_text("Daily note at root.")
    (tmp_path / ".obsidian" / "config.md").write_text("internal")
    (tmp_path / ".trash" / "old.md").write_text("trashed")
    return tmp_path


@pytest.fixture
def git_vault(vault: Path) -> Path:
    """Vault initialized as a git repo with three commits."""
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

    def run(*args: str) -> None:
        subprocess.run(["git", "-C", str(vault), *args], check=True, env=env,
                       capture_output=True)

    run("init", "-q", "-b", "main")
    run("add", "-A")
    run("commit", "-q", "-m", "initial")
    (vault / "epsilon.md").write_text("new note")
    run("add", "-A")
    run("commit", "-q", "-m", "add epsilon")
    (vault / "alpha.md").write_text("AAA BBB CCC modified")
    run("add", "-A")
    run("commit", "-q", "-m", "modify alpha")
    return vault


@pytest.fixture
def client(vault: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with settings.vault_path and api_key overridden, DB calls mocked."""
    monkeypatch.setenv("BLACKGLASS_VAULT_PATH", str(vault))
    monkeypatch.setenv("BLACKGLASS_API_KEY", "test-key")
    monkeypatch.setenv("POSTGRES_PASSWORD", "ignored")

    # Re-import settings module so env vars are read fresh.
    from blackglass_server import config as cfg_mod
    importlib.reload(cfg_mod)

    # importlib.reload creates a new settings object in cfg_mod, but every
    # other module (auth, routes, etc.) already holds a reference to the
    # original settings object via `from .config import settings`. We must
    # also patch the attributes on the original shared object so those
    # in-flight references see the test values.
    from blackglass_server.config import settings as original_settings
    monkeypatch.setattr(original_settings, "vault_path", vault)
    monkeypatch.setattr(original_settings, "api_key", "test-key")

    # Patch DB hooks to no-ops; specific tests can override.
    from blackglass_server import db as db_mod
    from blackglass_server import main as main_mod

    async def _no_pool() -> None:
        return None

    # Defense-in-depth: patch the module so lazy importers see no-ops.
    monkeypatch.setattr(db_mod, "init_pool", _no_pool)
    monkeypatch.setattr(db_mod, "close_pool", _no_pool)

    # Critical: main.py does `from .db import init_pool, close_pool` at import
    # time, so lifespan holds references to the original callables, not the
    # module attributes. Patch those bound names in main directly.
    monkeypatch.setattr(main_mod, "init_pool", _no_pool)
    monkeypatch.setattr(main_mod, "close_pool", _no_pool)

    from blackglass_server.main import app
    return TestClient(app, headers={"X-API-Key": "test-key"})
