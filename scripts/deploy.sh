#!/usr/bin/env bash
# Deploy blackglass to botvinnik.
#
# Usage:
#   ./scripts/deploy.sh [--sync-deps]
#
# --sync-deps: run `uv sync` after pulling (needed when pyproject.toml or
#              uv.lock changed; skipped by default)

set -euo pipefail

LOCAL_REPO="$HOME/Brian_Code/blackglass"
REMOTE_REPO="/home/fishhouses/Brian_Code/blackglass"
SERVER_SUBDIR="blackglass-server"
SERVICE="blackglass"
PORT=8083

SYNC_DEPS=0
for arg in "$@"; do
    case "$arg" in
        --sync-deps) SYNC_DEPS=1 ;;
        *) echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

echo "==> pushing to origin..."
git -C "$LOCAL_REPO" push

echo "==> [botvinnik] pulling code..."
ssh botvinnik "git -C $REMOTE_REPO pull --ff-only https://${GITHUB_PERSONAL_TOKEN}@github.com/acesanderson/blackglass.git"

if [[ "$SYNC_DEPS" -eq 1 ]]; then
    echo "==> [botvinnik] syncing deps..."
    ssh botvinnik "cd $REMOTE_REPO/$SERVER_SUBDIR && uv sync"
fi

echo "==> [botvinnik] restarting $SERVICE..."
ssh botvinnik "sudo systemctl restart $SERVICE"

echo -n "==> [botvinnik] waiting for $SERVICE on :$PORT ... "
for i in $(seq 1 20); do
    if ssh botvinnik "curl -sf http://localhost:$PORT/health" > /dev/null 2>&1; then
        echo "up"
        break
    fi
    if [[ $i -eq 20 ]]; then
        echo "TIMEOUT after 20s"
        echo "    run: ssh botvinnik 'journalctl -u $SERVICE -n 30'"
        exit 1
    fi
    sleep 1
done

echo "==> deploy complete"
