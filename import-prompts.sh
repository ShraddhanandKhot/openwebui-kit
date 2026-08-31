#!/usr/bin/env bash
# import-prompts.sh — register bundled Prompts into OpenWebUI
# Usage: ./import-prompts.sh <your-admin-api-key>
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: ./import-prompts.sh <your-admin-api-key>"
    echo "  (get the key at: Settings → Admin Panel → API Keys → Generate)"
    exit 1
fi
KEY="$1"
PORT="${OPENWEBUI_PORT:-8080}"
BASE="http://localhost:$PORT"

echo "Importing prompts into OpenWebUI at $BASE ..."

if [ ! -d "content/prompts" ]; then
    echo "  (no prompts bundled in this kit)"
    exit 0
fi

for jf in content/prompts/*.json; do
    [ -f "$jf" ] || continue
    python3 - "$BASE" "$KEY" "$jf" <<'PY'
import sys, json, urllib.request, urllib.error
base, key, path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    d = json.load(f)
payload = {
    "command": d.get("command", ""),
    "name": d.get("name", ""),
    "content": d.get("content", ""),
    "meta": d.get("meta", {}),
}
req = urllib.request.Request(f"{base}/api/v1/prompts/create",
    data=json.dumps(payload).encode(),
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    method="POST")
try:
    with urllib.request.urlopen(req) as resp:
        print(f"      ✓ prompt: /{payload['command']} (HTTP {resp.status})")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    if e.code == 400 and "already" in body.lower():
        print(f"      • prompt /{payload['command']} already exists (skipped)")
    else:
        print(f"      ✗ prompt /{payload['command']} failed: HTTP {e.code} {body[:200]}")
PY
done

echo
echo "Done. Your prompts appear with / in the chat input."
