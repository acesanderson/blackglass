from __future__ import annotations
import hashlib
import subprocess
import time
from fastapi import APIRouter, Depends, HTTPException
from ..auth import require_api_key
from ..config import settings
from ..vault import list_files
from ..db import get_indexed_hashes, upsert_embedding
from ..embeddings import embed_batch
from ..observability import record_sync

router = APIRouter(prefix="/vault", dependencies=[Depends(require_api_key)])

_MAX_EMBED_CHARS = 2000


@router.post("/sync")
async def sync_vault() -> dict:
    started = time.time()
    result = subprocess.run(
        ["git", "pull", "--ff-only"],
        cwd=settings.vault_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        record_sync({
            "started_at": started,
            "completed_at": time.time(),
            "duration_seconds": round(time.time() - started, 2),
            "files_checked": 0,
            "files_indexed": 0,
            "ok": False,
            "error": result.stderr.strip(),
        })
        raise HTTPException(status_code=500, detail=result.stderr.strip())

    files = list_files(settings.vault_path)
    indexed = await get_indexed_hashes()

    to_index: list[tuple[str, str, str]] = []
    for f in files:
        path = f["path"]
        content = (settings.vault_path / path).read_text(encoding="utf-8", errors="ignore")
        h = hashlib.sha256(content.encode()).hexdigest()
        if indexed.get(path) != h:
            to_index.append((path, content, h))

    batch_size = 4
    indexed_count = 0
    try:
        for i in range(0, len(to_index), batch_size):
            batch = to_index[i : i + batch_size]
            paths = [b[0] for b in batch]
            texts = [b[1][:_MAX_EMBED_CHARS] for b in batch]
            hashes = [b[2] for b in batch]
            # Backwater returns embeddings in the same order as the input documents
            embeddings = await embed_batch(texts, paths)
            for path, h, emb in zip(paths, hashes, embeddings):
                await upsert_embedding(path, h, emb)
                indexed_count += 1
    except Exception as exc:
        record_sync({
            "started_at": started,
            "completed_at": time.time(),
            "duration_seconds": round(time.time() - started, 2),
            "files_checked": len(files),
            "files_indexed": indexed_count,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        })
        raise

    record_sync({
        "started_at": started,
        "completed_at": time.time(),
        "duration_seconds": round(time.time() - started, 2),
        "files_checked": len(files),
        "files_indexed": indexed_count,
        "ok": True,
        "error": None,
    })
    return {
        "git": result.stdout.strip(),
        "files_checked": len(files),
        "files_indexed": indexed_count,
    }
