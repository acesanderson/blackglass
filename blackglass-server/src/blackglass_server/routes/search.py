from __future__ import annotations
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
