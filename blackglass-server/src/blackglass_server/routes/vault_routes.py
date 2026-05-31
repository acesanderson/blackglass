from __future__ import annotations
from fastapi import APIRouter, Body, Depends, HTTPException
from ..auth import require_api_key
from ..config import settings
from ..vault import (
    list_files,
    list_tags,
    compute_backlinks,
    list_periodic_notes,
    today_in_tz,
    yesterday_in_tz,
    ensure_daily_note,
    read_note,
    note_meta,
)

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


@router.get("/periodic/today")
def periodic_today() -> dict:
    date_str = today_in_tz(settings.tz)
    _, created = ensure_daily_note(settings.vault_path, date_str)
    note = read_note(settings.vault_path, f"{date_str}.md")
    note["created"] = created
    return note


@router.get("/periodic/yesterday")
def periodic_yesterday() -> dict:
    date_str = yesterday_in_tz(settings.tz)
    _, created = ensure_daily_note(settings.vault_path, date_str)
    note = read_note(settings.vault_path, f"{date_str}.md")
    note["created"] = created
    return note


@router.get("/periodic/by-date/{date_str}")
def periodic_by_date(date_str: str) -> dict:
    try:
        _, created = ensure_daily_note(settings.vault_path, date_str)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    note = read_note(settings.vault_path, f"{date_str}.md")
    note["created"] = created
    return note


@router.post("/periodic/today/append")
def periodic_today_append(content: str = Body(..., embed=True)) -> dict:
    date_str = today_in_tz(settings.tz)
    p, _ = ensure_daily_note(settings.vault_path, date_str)
    with p.open("a", encoding="utf-8") as f:
        f.write(content)
    return read_note(settings.vault_path, f"{date_str}.md")
