from __future__ import annotations


def test_hybrid_combines_text_and_semantic(client, monkeypatch):
    from blackglass_server.routes import search as sroute
    async def embed(text): return [0.0] * 768
    async def sem(emb, limit=10):
        return [
            {"path": "alpha.md", "score": 0.9},
            {"path": "beta.md", "score": 0.7},
        ]
    monkeypatch.setattr(sroute, "embed_text", embed)
    monkeypatch.setattr(sroute, "semantic_search", sem)
    r = client.get("/vault/hybrid-search", params={"q": "AAA", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    hits = body["results"]
    paths = [h["path"] for h in hits]
    assert "alpha.md" in paths
    alpha = next(h for h in hits if h["path"] == "alpha.md")
    assert "text" in alpha["sources"] or "semantic" in alpha["sources"]
    assert alpha["sources"] == sorted(alpha["sources"])
    assert "snippet" in alpha


def test_hybrid_sources_sorted_alpha(client, monkeypatch):
    from blackglass_server.routes import search as sroute
    async def embed(text): return [0.0] * 768
    async def sem(emb, limit=10): return [{"path": "alpha.md", "score": 0.9}]
    monkeypatch.setattr(sroute, "embed_text", embed)
    monkeypatch.setattr(sroute, "semantic_search", sem)
    r = client.get("/vault/hybrid-search", params={"q": "AAA"})
    alpha = next(h for h in r.json()["results"] if h["path"] == "alpha.md")
    assert alpha["sources"] == ["semantic", "text"]


def test_hybrid_backwater_down_returns_degraded(client, monkeypatch):
    from blackglass_server.routes import search as sroute
    import httpx
    async def embed(text):
        raise httpx.ConnectError("backwater down")
    async def sem(emb, limit=10): return []
    monkeypatch.setattr(sroute, "embed_text", embed)
    monkeypatch.setattr(sroute, "semantic_search", sem)
    r = client.get("/vault/hybrid-search", params={"q": "AAA"})
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] == "semantic_unavailable"
    assert any(h["path"] == "alpha.md" for h in body["results"])


def test_hybrid_empty_q_400(client):
    r = client.get("/vault/hybrid-search", params={"q": ""})
    assert r.status_code == 400


def test_hybrid_backwater_http_error_propagates(client, monkeypatch):
    from blackglass_server.routes import search as sroute
    from fastapi.testclient import TestClient
    from blackglass_server.main import app
    import httpx
    async def embed(text):
        req = httpx.Request("POST", "http://backwater/")
        resp = httpx.Response(500, request=req)
        raise httpx.HTTPStatusError("500", request=req, response=resp)
    async def sem(emb, limit=10): return []
    monkeypatch.setattr(sroute, "embed_text", embed)
    monkeypatch.setattr(sroute, "semantic_search", sem)
    # raise_server_exceptions=False so unhandled exceptions surface as 500 responses
    no_raise_client = TestClient(app, headers={"X-API-Key": "test-key"},
                                 raise_server_exceptions=False)
    r = no_raise_client.get("/vault/hybrid-search", params={"q": "AAA"})
    # 4xx/5xx from backwater is a real bug, not a degraded condition
    assert r.status_code >= 500
