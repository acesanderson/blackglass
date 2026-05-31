from __future__ import annotations


def test_client_fixture_health_works(client):
    """Exercises lifespan startup; fails with Postgres error if DB mocking is broken."""
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
