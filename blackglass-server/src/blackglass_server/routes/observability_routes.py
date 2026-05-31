from __future__ import annotations
import os
import subprocess
import time
from fastapi import APIRouter, Depends, Query
from ..auth import require_api_key
from ..config import settings
from ..db import get_pool
from ..embeddings import _MODEL
from ..observability import ring_buffer, started_at, last_sync


router = APIRouter(dependencies=[Depends(require_api_key)])

_SYSTEMD_UNIT = "blackglass"
_JOURNALCTL = "/usr/bin/journalctl"


@router.get("/status")
async def status() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        indexed_count = await conn.fetchval("SELECT COUNT(*) FROM vault_embeddings")

    now = time.time()
    return {
        "name": "blackglass",
        "version": "0.1.0",
        "pid": os.getpid(),
        "started_at": started_at(),
        "uptime_seconds": round(now - started_at(), 1),
        "vault_path": str(settings.vault_path),
        "backwater_url": settings.backwater_url,
        "embedding_model": _MODEL,
        "indexed_count": int(indexed_count or 0),
        "last_sync": last_sync(),
    }


@router.get("/logs/last")
def logs_last(n: int = Query(default=50, ge=1, le=200)) -> dict:
    entries = ring_buffer.get_records(n)
    return {
        "entries": entries,
        "total_buffered": len(ring_buffer._buffer),
        "capacity": ring_buffer.capacity,
    }


@router.get("/logs/journal")
def logs_journal(n: int = Query(default=100, ge=1, le=2000)) -> dict:
    try:
        result = subprocess.run(
            [_JOURNALCTL, "-u", _SYSTEMD_UNIT, "-n", str(n), "--no-pager"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return {"unit": _SYSTEMD_UNIT, "n_requested": n, "lines": [], "error": "journalctl not available"}
    except subprocess.TimeoutExpired:
        return {"unit": _SYSTEMD_UNIT, "n_requested": n, "lines": [], "error": "journalctl timed out"}

    if result.returncode != 0:
        return {
            "unit": _SYSTEMD_UNIT,
            "n_requested": n,
            "lines": [],
            "error": result.stderr.strip() or f"journalctl exited {result.returncode}",
        }
    return {"unit": _SYSTEMD_UNIT, "n_requested": n, "lines": result.stdout.splitlines()}
