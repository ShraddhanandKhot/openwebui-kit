#!/usr/bin/env bash
# import-models.sh — register bundled Model configs into OpenWebUI
# The client connects their OWN provider/API key — no keys are shipped.
# Usage: ./import-models.sh <your-admin-api-key>
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: ./import-models.sh <your-admin-api-key>"
    echo "  (get the key at: Settings → Admin Panel → API Keys → Generate)"
    exit 1
fi
KEY="$1"
PORT="${OPENWEBUI_PORT:-8080}"
BASE="http://localhost:$PORT"

echo "Importing models into OpenWebUI at $BASE ..."

if [ ! -d "content/models" ]; then
    echo "  (no models bundled in this kit)"
    exit 0
fi

for jf in content/models/*.json; do
    [ -f "$jf" ] || continue
    python3 - "$BASE" "$KEY" "$jf" <<'PY'
import sys, json, urllib.request, urllib.error
base, key, path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    d = json.load(f)

# params/meta are stored as JSON strings in the DB — parse to dicts
def to_obj(v):
    if isinstance(v, str):
        try:
            return json.loads(v) if v.strip() else {}
        except Exception:
            return {}
    return v or {}

payload = {
    "id": str(d.get("id", "")),
    "base_model_id": d.get("base_model_id"),
    "name": d.get("name", ""),
    "meta": to_obj(d.get("meta")),
    "params": to_obj(d.get("params")),
    "is_active": bool(d.get("is_active", True)),
}
req = urllib.request.Request(f"{base}/api/v1/models/create",
    data=json.dumps(payload).encode(),
    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    method="POST")
try:
    with urllib.request.urlopen(req) as resp:
        print(f"      ✓ model: {payload['id']} (HTTP {resp.status})")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    if e.code == 400 and "already" in body.lower():
        print(f"      • model {payload['id']} already exists (skipped)")
    else:
        print(f"      ✗ model {payload['id']} failed: HTTP {e.code} {body[:200]}")
PY
done

echo
echo "Done. Models are in Workspace → Models."
echo "NOTE: each model uses a base model from your provider — connect your"
echo "OpenAI / OpenRouter / Ollama key in Settings → Model Connections first"
echo "so the base models are available."
