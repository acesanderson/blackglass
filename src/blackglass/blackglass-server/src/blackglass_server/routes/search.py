from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from ..auth import require_api_key
from ..config import settings
from ..vault import fulltext_search

router = APIRouter(prefix="/vault", dependencies=[Depends(require_api_key)])


@router.get("/search")
def text_search(q: str = Query(..., min_length=1)) -> list[dict]:
    return fulltext_search(settings.vault_path, q)
