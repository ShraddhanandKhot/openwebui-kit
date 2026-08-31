#!/usr/bin/env bash
# import-skills.sh — register bundled Skills into OpenWebUI
# Usage: ./import-skills.sh <your-admin-api-key>
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: ./import-skills.sh <your-admin-api-key>"
    echo "  (get the key at: Settings → Admin Panel → API Keys → Generate)"
    exit 1
fi
KEY="$1"
PORT="${OPENWEBUI_PORT:-8080}"
BASE="http://localhost:$PORT"

echo "Importing skills into OpenWebUI at $BASE ..."

if [ ! -d "content/skills" ]; then
    echo "  (no skills bundled in this kit)"
    exit 0
fi

for jf in content/skills/*.json; do
    [ -f "$jf" ] || continue
    python3 - "$BASE" "$KEY" "$jf" <<'PY'
import sys, json, urllib.request, urllib.error
base, key, path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    d = json.load(f)
payload = {
    "id": str(d.get("id", "")),
    "name": d.get("name", ""),
    "description": d.get("description", ""),
    "content": d.get("content", ""),
    "meta": d.get("meta", {}),
    "is_active": bool(d.get("is_active", True)),
}
req = urllib.request.Request(f"{base}/api/v1/skills/create",
    data=json.dumps(payload).encode(),
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    method="POST")
try:
    with urllib.request.urlopen(req) as resp:
        print(f"      ✓ skill: {payload['id']} (HTTP {resp.status})")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    if e.code == 400 and "already" in body.lower():
        print(f"      • skill {payload['id']} already exists (skipped)")
    else:
        print(f"      ✗ skill {payload['id']} failed: HTTP {e.code} {body[:200]}")
PY
done

echo
echo "Done. Your skills are now in Workspace → Skills."
