#!/usr/bin/env bash
# uninstall.sh — remove OpenWebUI (container + image)
# Your ./data folder is KEPT by default (add --delete-data to remove it too).
set -euo pipefail

echo "Removing OpenWebUI container..."
docker compose down

if [ "${1:-}" = "--delete-data" ]; then
    echo "Deleting ./data ..."
    rm -rf data
    echo "Data deleted."
fi

echo
echo "  ✓ OpenWebUI removed."
echo "  To also delete your data: ./uninstall.sh --delete-data"
