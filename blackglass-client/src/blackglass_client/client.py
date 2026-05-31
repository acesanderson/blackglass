from __future__ import annotations
import os
import httpx

_DEFAULT_URL = "http://172.16.0.3:8083"


def _client() -> httpx.Client:
    url = os.environ.get("BLACKGLASS_URL", _DEFAULT_URL)
    key = os.environ.get("BLACKGLASS_API_KEY", "")
    return httpx.Client(base_url=url, headers={"X-API-Key": key}, timeout=60.0)


def request(method: str, path: str, **kwargs) -> dict | list | None:
    with _client() as c:
        resp = c.request(method, path, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()
