#!/usr/bin/env bash
# import-content.sh — register bundled Workspace content into OpenWebUI
# Handles: Tools, Skills, Prompts (from the kit's content/ + tools/ folders)
# Usage: ./import-content.sh <your-admin-api-key>
# The admin key is at: Settings → Admin Panel → API Keys → Generate
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: ./import-content.sh <your-admin-api-key>"
    echo "  (get the key at: Settings → Admin Panel → API Keys → Generate)"
    exit 1
fi
KEY="$1"
PORT="${OPENWEBUI_PORT:-8080}"
BASE="http://localhost:$PORT"

echo "Importing content into OpenWebUI at $BASE ..."
mkdir -p data

# 1. AnyDoc pipeline modules must live in the data volume where the tool
#    imports them from (/app/backend/data/anydoc_py).
if [ -d "tools/anydoc_py" ]; then
    mkdir -p data/anydoc_py
    cp tools/anydoc_py/*.py data/anydoc_py/
    echo "  ✓ AnyDoc pipeline modules installed into ./data/anydoc_py/"
fi

# 2. Register each bundled tool via the API
for toolfile in tools/*.py; do
    [ -f "$toolfile" ] || continue
    python3 - "$BASE" "$KEY" "$toolfile" "tools" <<'PY'
import sys, json, urllib.request, urllib.error
base, key, path, kind = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
with open(path) as f:
    content = f.read()
item_id = path.rsplit("/", 1)[-1].rsplit(".py", 1)[0]
endpoint = "tools" if kind == "tools" else "functions"
payload = {"id": item_id, "name": item_id, "content": content,
           "meta": {"description": item_id}}
req = urllib.request.Request(f"{base}/api/v1/{endpoint}/create",
    data=json.dumps(payload).encode(),
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    method="POST")
try:
    with urllib.request.urlopen(req) as resp:
        print(f"      ✓ {kind}: {item_id} (HTTP {resp.status})")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    if e.code == 400 and "already" in body.lower():
        print(f"      • {item_id} already exists (skipped)")
    else:
        print(f"      ✗ {item_id} failed: HTTP {e.code} {body[:200]}")
PY
done

# 3. Import Skills (content/skills/*.json → POST /api/v1/functions/create)
if [ -d "content/skills" ]; then
    for jf in content/skills/*.json; do
        [ -f "$jf" ] || continue
        python3 - "$BASE" "$KEY" "$jf" "skills" <<'PY'
import sys, json, urllib.request, urllib.error
base, key, path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    d = json.load(f)
payload = {
    "id": str(d.get("id", "")),
    "name": d.get("name", ""),
    "type": "skill",
    "content": d.get("content", ""),
    "meta": d.get("meta", {}),
    "is_active": bool(d.get("is_active", True)),
    "is_global": bool(d.get("is_global", False)),
}
req = urllib.request.Request(f"{base}/api/v1/functions/create",
    data=json.dumps(payload).encode(),
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    method="POST")
try:
    with urllib.request.urlopen(req) as resp:
        print(f"      ✓ skill: {payload['name'] or payload['id']} (HTTP {resp.status})")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    if e.code == 400 and "already" in body.lower():
        print(f"      • skill {payload['id']} already exists (skipped)")
    else:
        print(f"      ✗ skill {payload['id']} failed: HTTP {e.code} {body[:200]}")
PY
    done
fi

# 4. Import Prompts (content/prompts/*.json → POST /api/v1/prompts/create)
if [ -d "content/prompts" ]; then
    for jf in content/prompts/*.json; do
        [ -f "$jf" ] || continue
        python3 - "$BASE" "$KEY" "$jf" "prompts" <<'PY'
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
fi

echo
echo "Done. Tools are in Workspace → Tools; Skills in Workspace → Skills;"
echo "Prompts appear with / in the chat input."
