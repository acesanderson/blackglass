from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from ..auth import require_api_key
from ..config import settings
from ..vault import fulltext_search
from ..db import semantic_search as db_semantic_search
from ..embeddings import embed_text

router = APIRouter(prefix="/vault", dependencies=[Depends(require_api_key)])


@router.get("/search")
def text_search(q: str = Query(..., min_length=1)) -> list[dict]:
    return fulltext_search(settings.vault_path, q)


@router.get("/semantic-search")
async def semantic_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
) -> list[dict]:
    embedding = await embed_text(q)
    return await db_semantic_search(embedding, limit)
