from __future__ import annotations
import datetime
import zoneinfo


def _today_in_tz(tz: str) -> str:
    return datetime.datetime.now(zoneinfo.ZoneInfo(tz)).strftime("%Y-%m-%d")


def test_today_auto_creates_on_first_get(client, vault):
    today = _today_in_tz("UTC")
    target = vault / f"{today}.md"
    if target.exists():
        target.unlink()
    r = client.get("/vault/periodic/today")
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True
    assert body["path"] == f"{today}.md"
    assert target.exists()


def test_today_second_get_not_created(client, vault):
    today = _today_in_tz("UTC")
    (vault / f"{today}.md").write_text("exists")
    r = client.get("/vault/periodic/today")
    assert r.json()["created"] is False


def test_by_date_invalid_format_400(client):
    r = client.get("/vault/periodic/by-date/2026-13-01")
    assert r.status_code == 400


def test_by_date_out_of_range_400(client):
    r = client.get("/vault/periodic/by-date/1969-12-31")
    assert r.status_code == 400
    r2 = client.get("/vault/periodic/by-date/2100-01-01")
    assert r2.status_code == 400


def test_append_creates_then_appends(client, vault):
    today = _today_in_tz("UTC")
    target = vault / f"{today}.md"
    if target.exists():
        target.unlink()
    r1 = client.post("/vault/periodic/today/append", json={"content": "one\n"})
    assert r1.status_code == 200
    r2 = client.post("/vault/periodic/today/append", json={"content": "two\n"})
    assert r2.status_code == 200
    assert target.read_text() == "one\ntwo\n"
