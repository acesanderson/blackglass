from __future__ import annotations
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from ..auth import require_api_key
from ..config import settings
from ..vault import _resolve, fulltext_search
from ..text_utils import snippet_from_body, split_frontmatter
from ..db import semantic_search
from ..embeddings import embed_text

router = APIRouter(prefix="/vault", dependencies=[Depends(require_api_key)])

_MAX_SNIPPET = 1000


def _snippet_for_path(path: str, snippet_chars: int) -> str:
    if snippet_chars <= 0:
        return ""
    try:
        resolved = _resolve(settings.vault_path, path)
        text = resolved.read_text(encoding="utf-8", errors="ignore")
    except (OSError, ValueError):
        return ""
    _, body = split_frontmatter(text)
    return snippet_from_body(body, snippet_chars)


# Mutates `hits` in-place. Safe for current callers (fresh dicts from fulltext_search /
# semantic_search); revisit if a future caller passes pre-built dicts they reuse.
def _attach_snippet(hits: list[dict], snippet_chars: int) -> list[dict]:
    if snippet_chars <= 0:
        return hits
    for h in hits:
        h["snippet"] = _snippet_for_path(h["path"], snippet_chars)
    return hits


@router.get("/search")
def search(
    q: str = Query(...),
    snippet_chars: int = Query(default=300, ge=0, le=_MAX_SNIPPET),
) -> list[dict]:
    if not q:
        raise HTTPException(status_code=400, detail="q is required")
    hits = fulltext_search(settings.vault_path, q)
    return _attach_snippet(hits, snippet_chars)


@router.get("/semantic-search")
async def semantic(
    q: str = Query(...),
    limit: int = Query(default=10, ge=1, le=100),
    snippet_chars: int = Query(default=300, ge=0, le=_MAX_SNIPPET),
) -> list[dict]:
    if not q:
        raise HTTPException(status_code=400, detail="q is required")
    emb = await embed_text(q)
    hits = await semantic_search(emb, limit=limit)
    return _attach_snippet(hits, snippet_chars)


def _rrf(rank: int, k: int) -> float:
    return 1.0 / (k + rank)


@router.get("/hybrid-search")
async def hybrid_search(
    q: str = Query(...),
    limit: int = Query(default=10, ge=1, le=100),
    snippet_chars: int = Query(default=300, ge=0, le=_MAX_SNIPPET),
    k: int = Query(default=60, ge=1, le=1000),
) -> dict:
    if not q:
        raise HTTPException(status_code=400, detail="q is required")

    pull = limit * 3
    text_hits = fulltext_search(settings.vault_path, q)[:pull]

    sem_hits: list[dict] = []
    degraded: str | None = None
    try:
        emb = await embed_text(q)
        sem_hits = await semantic_search(emb, limit=pull)
    except httpx.RequestError:
        degraded = "semantic_unavailable"

    scores: dict[str, dict] = {}
    for i, h in enumerate(text_hits, start=1):
        path = h["path"]
        bucket = scores.setdefault(path, {"path": path, "score": 0.0,
                                          "sources": set(), "text_rank": None,
                                          "semantic_rank": None,
                                          "text_excerpt": h.get("excerpt")})
        bucket["score"] += _rrf(i, k)
        bucket["sources"].add("text")
        bucket["text_rank"] = i

    for i, h in enumerate(sem_hits, start=1):
        path = h["path"]
        bucket = scores.setdefault(path, {"path": path, "score": 0.0,
                                          "sources": set(), "text_rank": None,
                                          "semantic_rank": None,
                                          "text_excerpt": None})
        bucket["score"] += _rrf(i, k)
        bucket["sources"].add("semantic")
        bucket["semantic_rank"] = i

    ranked = sorted(scores.values(), key=lambda b: b["score"], reverse=True)[:limit]
    out = []
    for b in ranked:
        snippet = ""
        if snippet_chars > 0:
            if b["text_excerpt"]:
                snippet = b["text_excerpt"][:snippet_chars]
            else:
                snippet = _snippet_for_path(b["path"], snippet_chars)
        out.append({
            "path": b["path"],
            "score": b["score"],
            "snippet": snippet,
            "sources": sorted(b["sources"]),
            "text_rank": b["text_rank"],
            "semantic_rank": b["semantic_rank"],
        })
    return {"results": out, "degraded": degraded}
