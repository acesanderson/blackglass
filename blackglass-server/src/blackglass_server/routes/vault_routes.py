from __future__ import annotations
from pathlib import PurePosixPath
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from ..auth import require_api_key
from ..config import settings
from ..vault import (
    list_files,
    list_files_filtered,
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
def get_files(request: Request, limit: int | None = None):
    raw = request.query_params
    tag_list = [v for k, v in raw.multi_items() if k == "tag"]
    fm_filters: dict[str, str] = {}
    seen_fm: set[str] = set()
    for key, val in raw.multi_items():
        if not key.startswith("fm."):
            continue
        bare = key[3:]
        if "." in bare:
            raise HTTPException(status_code=400, detail="nested keys not supported")
        if bare in seen_fm:
            raise HTTPException(status_code=400, detail=f"duplicate filter key: fm.{bare}")
        seen_fm.add(bare)
        fm_filters[bare] = val
    path_glob = raw.get("path_glob")
    if path_glob is not None and ".." in PurePosixPath(path_glob).parts:
        raise HTTPException(status_code=400, detail="path_glob may not contain '..'")
    has_filter = bool(tag_list or fm_filters or path_glob or limit)
    if not has_filter:
        return list_files(settings.vault_path)
    filtered, total, all_count = list_files_filtered(
        settings.vault_path,
        tags=tag_list,
        fm_filters=fm_filters,
        path_glob=path_glob,
        limit=limit,
    )
    return {"files": filtered, "total": total, "filtered_from": all_count}


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
