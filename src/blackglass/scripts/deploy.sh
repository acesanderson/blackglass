#!/usr/bin/env bash
set -euo pipefail

REMOTE="fishhouses@172.16.0.3"
REMOTE_DIR="~/services/blackglass"
SERVER_SUBDIR="src/blackglass/blackglass-server"
BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "==> Pushing $BRANCH to GitHub"
git push origin "$BRANCH"

echo "==> Pulling and syncing on botvinnik"
ssh -p 2222 "$REMOTE" bash <<EOF
set -euo pipefail
cd $REMOTE_DIR
git pull --ff-only
cd $SERVER_SUBDIR
uv sync
echo "Deploy complete."
EOF

echo ""
echo "==> Done. To restart the service:"
echo "    ssh -p 2222 $REMOTE 'sudo systemctl restart blackglass'"
