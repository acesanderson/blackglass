from __future__ import annotations
import pytest
from blackglass_server.text_utils import snippet_from_body


def test_snippet_truncates_at_whitespace():
    body = "alpha beta gamma " * 50
    snip = snippet_from_body(body, 50)
    assert len(snip) <= 50
    assert not snip.endswith("alph") and not snip.endswith("alp")
    assert snip.rstrip() == snip


def test_snippet_shorter_than_limit_returns_full():
    body = "tiny"
    assert snippet_from_body(body, 50) == "tiny"


def test_snippet_zero_chars_returns_empty():
    assert snippet_from_body("anything", 0) == ""


def test_snippet_strips_leading_whitespace():
    body = "\n\n  alpha beta"
    snip = snippet_from_body(body, 50)
    assert snip.startswith("alpha")


def test_snippet_hard_truncates_when_no_word_boundary():
    body = "A" * 200
    snip = snippet_from_body(body, 50)
    assert len(snip) == 50


def test_search_returns_snippet(client):
    r = client.get("/vault/search", params={"q": "AAA", "snippet_chars": 60})
    assert r.status_code == 200
    hits = r.json()
    paths = [h["path"] for h in hits]
    assert "alpha.md" in paths
    alpha_hit = next(h for h in hits if h["path"] == "alpha.md")
    assert "snippet" in alpha_hit
    assert len(alpha_hit["snippet"]) <= 60
    assert "AAA" in alpha_hit["snippet"]


def test_search_snippet_chars_zero_omits_field(client):
    r = client.get("/vault/search", params={"q": "AAA", "snippet_chars": 0})
    assert r.status_code == 200
    for hit in r.json():
        assert "snippet" not in hit


def test_search_default_snippet_chars_is_300(client):
    r = client.get("/vault/search", params={"q": "AAA"})
    hits = r.json()
    alpha_hit = next(h for h in hits if h["path"] == "alpha.md")
    assert "snippet" in alpha_hit
    assert len(alpha_hit["snippet"]) <= 300


def test_search_empty_q_returns_400(client):
    r = client.get("/vault/search", params={"q": ""})
    assert r.status_code == 400


def test_semantic_search_attaches_snippet(client, monkeypatch):
    async def fake_embed_text(text):
        return [0.0] * 768
    async def fake_semantic_search(emb, limit=10):
        return [{"path": "alpha.md", "score": 0.9}]
    from blackglass_server.routes import search as sroute
    monkeypatch.setattr(sroute, "embed_text", fake_embed_text)
    monkeypatch.setattr(sroute, "semantic_search", fake_semantic_search)
    r = client.get("/vault/semantic-search", params={"q": "x", "snippet_chars": 80})
    assert r.status_code == 200
    hit = r.json()[0]
    assert hit["path"] == "alpha.md"
    assert "snippet" in hit
    assert "AAA" in hit["snippet"]


def test_semantic_search_missing_file_snippet_empty(client, monkeypatch):
    async def fake_embed_text(text):
        return [0.0] * 768
    async def fake_semantic_search(emb, limit=10):
        return [{"path": "ghost.md", "score": 0.5}]
    from blackglass_server.routes import search as sroute
    monkeypatch.setattr(sroute, "embed_text", fake_embed_text)
    monkeypatch.setattr(sroute, "semantic_search", fake_semantic_search)
    r = client.get("/vault/semantic-search", params={"q": "x"})
    hit = r.json()[0]
    assert hit["snippet"] == ""


def test_search_path_escape_snippet_empty(client, vault, monkeypatch):
    # If a search result somehow points outside the vault, snippet must be empty (not raise).
    async def fake_embed_text(text):
        return [0.0] * 768
    async def fake_semantic_search(emb, limit=10):
        return [{"path": "../escape.md", "score": 0.5}]
    from blackglass_server.routes import search as sroute
    monkeypatch.setattr(sroute, "embed_text", fake_embed_text)
    monkeypatch.setattr(sroute, "semantic_search", fake_semantic_search)
    r = client.get("/vault/semantic-search", params={"q": "x"})
    assert r.status_code == 200
    hit = r.json()[0]
    assert hit["snippet"] == ""
    assert hit["path"] == "../escape.md"
