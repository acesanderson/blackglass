"""
sync_vault — trigger blackglass vault sync (git pull + incremental re-index).

The sync endpoint is idempotent: it hashes every note and only re-embeds files
whose hash changed since the last run. Resumability is free — mid-run kills
leave already-indexed notes in Postgres; the next run skips them.

Usage:
    uv run --with httpx python jobs/sync_vault.py            # full run
    uv run --with httpx python jobs/sync_vault.py --cron     # health-gated (Cronicle)
    uv run --with httpx python jobs/sync_vault.py --dry-run  # print plan, exit
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).parent / "sync_vault.log"
STATUS_PATH = Path(__file__).parent / "sync_vault_status.json"

BLACKGLASS_URL = os.environ.get("BLACKGLASS_URL", "http://172.16.0.3:8083")
BLACKGLASS_API_KEY = os.environ.get("BLACKGLASS_API_KEY", "")

logger = logging.getLogger(__name__)
_shutdown = False


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_PATH),
        ],
    )


def handle_sigterm(signum, frame) -> None:
    global _shutdown
    _shutdown = True
    logger.info("SIGTERM received — will not start new work")


def health_check() -> bool:
    import httpx
    try:
        resp = httpx.get(f"{BLACKGLASS_URL}/health", timeout=10.0)
        ok = resp.status_code == 200
        if not ok:
            logger.warning(f"health check returned {resp.status_code}")
        return ok
    except Exception as e:
        logger.warning(f"health check failed: {e}")
        return False


def run(args: argparse.Namespace) -> None:
    import httpx
    logger.info(f"starting vault sync — {BLACKGLASS_URL}/vault/sync")
    resp = httpx.post(
        f"{BLACKGLASS_URL}/vault/sync",
        headers={"X-API-Key": BLACKGLASS_API_KEY},
        timeout=3600.0,
    )
    resp.raise_for_status()
    result = resp.json()
    git_out = result.get("git", "").strip()
    logger.info(f"git: {git_out or 'already up to date'}")
    logger.info(f"files checked: {result['files_checked']}  newly indexed: {result['files_indexed']}")


def write_status(status: str, **kwargs) -> None:
    STATUS_PATH.write_text(json.dumps({
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }))


def main() -> None:
    parser = argparse.ArgumentParser(description="Trigger blackglass vault sync")
    parser.add_argument("--cron", action="store_true", help="health-gate before running (for Cronicle)")
    parser.add_argument("--dry-run", action="store_true", help="print what would run and exit")
    args = parser.parse_args()

    setup_logging()
    signal.signal(signal.SIGTERM, handle_sigterm)

    if args.dry_run:
        logger.info(f"dry-run: would POST {BLACKGLASS_URL}/vault/sync")
        return

    if args.cron and not health_check():
        logger.info("health check failed — skipping (exit 0)")
        sys.exit(0)

    try:
        run(args)
        write_status("success")
    except Exception:
        logger.exception("unhandled exception")
        write_status("failure")
        sys.exit(1)


if __name__ == "__main__":
    main()
