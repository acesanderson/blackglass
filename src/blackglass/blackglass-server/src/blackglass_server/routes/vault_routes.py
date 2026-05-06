from __future__ import annotations
from fastapi import APIRouter, Depends
from ..auth import require_api_key
from ..config import settings
from ..vault import list_files, list_tags, compute_backlinks, list_periodic_notes

router = APIRouter(prefix="/vault", dependencies=[Depends(require_api_key)])


@router.get("/files")
def get_files() -> list[dict]:
    return list_files(settings.vault_path)


@router.get("/tags")
def get_tags() -> list[dict]:
    return list_tags(settings.vault_path)


@router.get("/periodic")
def get_periodic() -> list[dict]:
    return list_periodic_notes(settings.vault_path)


@router.get("/backlinks/{path:path}")
def get_backlinks(path: str) -> dict:
    bl = compute_backlinks(settings.vault_path, path)
    return {"path": path, "backlinks": bl}
