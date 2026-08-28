#!/usr/bin/env bash
# upgrade.sh — ONE-COMMAND update for OpenWebUI
# Pulls the newest image and restarts. Your data in ./data is untouched.
set -euo pipefail

echo "=============================================="
echo "  OpenWebUI — update"
echo "=============================================="

echo "[✓] Pulling newest image..."
docker compose pull

echo "[✓] Restarting..."
docker compose up -d

echo
echo "  ✓ OpenWebUI is updated."
echo "  Your data in ./data was NOT touched."
echo "=============================================="
