#!/usr/bin/env bash
# import-tools.sh — register the bundled Workspace Tools into OpenWebUI
# Usage: ./import-tools.sh <your-admin-api-key>
# The admin key is at: Settings → Admin Panel → API Keys → Generate
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: ./import-tools.sh <your-admin-api-key>"
    echo "  (get the key at: Settings → Admin Panel → API Keys → Generate)"
    exit 1
fi
KEY="$1"
PORT="${OPENWEBUI_PORT:-8080}"
BASE="http://localhost:$PORT"

echo "Importing tools into OpenWebUI at $BASE ..."

# 1. AnyDoc pipeline modules must live in the data volume where the tool
#    imports them from (/app/backend/data/anydoc_py).
if [ -d "tools/anydoc_py" ]; then
    mkdir -p data/anydoc_py
    cp tools/anydoc_py/*.py data/anydoc_py/
    echo "  ✓ AnyDoc pipeline modules installed into ./data/anydoc_py/"
fi

# 2. Register each bundled tool via the API
# Use a small python helper for the HTTP calls (portable, reliable)
for toolfile in tools/*.py; do
    [ -f "$toolfile" ] || continue
    id=$(basename "$toolfile" .py)
    echo "  → registering '$id' ..."
    python3 - "$BASE" "$KEY" "$toolfile" <<'PY'
import sys, json, urllib.request

base, key, path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    content = f.read()
tool_id = path.rsplit("/", 1)[-1].rsplit(".py", 1)[0]

payload = {
    "id": tool_id,
    "name": tool_id,
    "content": content,
    "meta": {"description": tool_id},
}
req = urllib.request.Request(
    f"{base}/api/v1/tools/create",
    data=json.dumps(payload).encode(),
    headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    },
    method="POST",
)
try:
    with urllib.request.urlopen(req) as resp:
        print(f"      ✓ {tool_id} registered (HTTP {resp.status})")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    if e.code == 400 and "already" in body.lower():
        print(f"      • {tool_id} already exists (skipped)")
    else:
        print(f"      ✗ {tool_id} failed: HTTP {e.code} {body}")
PY
done

echo
echo "Done. Your tools are now in Workspace → Tools."
echo "Attach them to a model from Workspace → Models → edit → Tools."
