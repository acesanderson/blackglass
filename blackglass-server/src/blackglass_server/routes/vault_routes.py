from __future__ import annotations
import datetime
import subprocess
import time as _time
from pathlib import PurePosixPath
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from ..auth import require_api_key
from ..config import settings
from ..git_utils import git_changes
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


_SKIP_DIRS = ("/.obsidian/", "/.trash/")


def _parse_since(since: str) -> float:
    try:
        return float(since)
    except ValueError:
        pass
    s = since.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(s).timestamp()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unparseable since: {since}") from exc


@router.get("/changes")
def vault_changes(
    since: str | None = None,
    days: int | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    include_diff_stats: bool = False,
) -> dict:
    if since is not None and days is not None:
        raise HTTPException(status_code=400, detail="pass either since or days, not both")
    if days is not None and (days < 1 or days > 365):
        raise HTTPException(status_code=400, detail="days must be in [1, 365]")
    if since is None and days is None:
        days = 7
    if days is not None:
        since_epoch = _time.time() - days * 86400
    else:
        since_epoch = _parse_since(since)

    if not (settings.vault_path / ".git").exists():
        raise HTTPException(status_code=400, detail="vault is not a git repository")

    try:
        commits = git_changes(settings.vault_path, since_epoch, include_diff_stats)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="git not available on server")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="git log timed out")
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    flat: list[dict] = []
    for c in commits:
        for ch in c["changes"]:
            normalized = "/" + ch["path"]
            if any(s in normalized for s in _SKIP_DIRS):
                continue
            flat.append({
                "path": ch["path"],
                "change": ch["change"],
                "commit": c["commit"][:7],
                "timestamp": c["timestamp"],
                "subject": c["subject"],
                "from_path": ch["from_path"],
                "diff_stats": ch.get("diff_stats"),
            })
    flat.sort(key=lambda x: x["timestamp"], reverse=True)
    truncated = len(flat) > limit
    return {
        "since": since_epoch,
        "limit": limit,
        "changes": flat[:limit],
        "truncated": truncated,
    }
