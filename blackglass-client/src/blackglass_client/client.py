from __future__ import annotations
import json
import os
import sys
import click
import httpx

_DEFAULT_URL = "http://172.16.0.3:8083"


def _client() -> httpx.Client:
    url = os.environ.get("BLACKGLASS_URL", _DEFAULT_URL)
    key = os.environ.get("BLACKGLASS_API_KEY", "")
    return httpx.Client(base_url=url, headers={"X-API-Key": key}, timeout=60.0)


def _extract_detail(resp: httpx.Response) -> object:
    try:
        body = resp.json()
    except ValueError:
        return resp.text
    if isinstance(body, dict) and "detail" in body:
        return body["detail"]
    return body


def request(method: str, path: str, **kwargs) -> dict | list | None:
    try:
        with _client() as c:
            resp = c.request(method, path, **kwargs)
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()
    except httpx.HTTPStatusError as exc:
        envelope = {
            "error": "http_error",
            "status": exc.response.status_code,
            "method": method,
            "path": path,
            "detail": _extract_detail(exc.response),
        }
        click.echo(json.dumps(envelope), err=True)
        sys.exit(4 if 400 <= exc.response.status_code < 500 else 5)
    except httpx.RequestError as exc:
        envelope = {
            "error": "transport_error",
            "status": None,
            "method": method,
            "path": path,
            "detail": f"{type(exc).__name__}: {exc}",
        }
        click.echo(json.dumps(envelope), err=True)
        sys.exit(1)
