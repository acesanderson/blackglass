from __future__ import annotations

import os
import pytest
import respx
from click.testing import CliRunner


BASE_URL = "http://test-server"
API_KEY = "test-key"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BLACKGLASS_URL", BASE_URL)
    monkeypatch.setenv("BLACKGLASS_API_KEY", API_KEY)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


@pytest.fixture
def mock_api():
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        yield router
