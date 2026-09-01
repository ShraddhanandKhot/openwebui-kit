#!/usr/bin/env bash
# install-sprynt.sh — one-line installer for the sprynt CLI
# Usage: curl -fsSL https://raw.githubusercontent.com/ShraddhanandKhot/openwebui-kit/main/install-sprynt.sh | sudo bash
set -euo pipefail

BIN="/usr/local/bin/sprynt"
VER="1.0"

echo "Installing sprynt CLI v$VER ..."

# Fetch the CLI script from the delivery repo
TMP=$(mktemp)
curl -fsSL -o "$TMP" \
  "https://raw.githubusercontent.com/ShraddhanandKhot/openwebui-kit/main/sprynt" \
  2>/dev/null || {
  echo "✗ Could not download sprynt CLI from GitHub"
  rm -f "$TMP"
  exit 1
}

sudo install -m 755 "$TMP" "$BIN"
rm -f "$TMP"

echo "  ✓ installed to $BIN"
echo ""
echo "Now cd into your kit folder and:"
echo "  sprynt install     # install OpenWebUI"
echo "  sprynt login <key> # save your admin API key"
echo "  sprynt import      # import all content"
echo "  sprynt help        # see all commands"