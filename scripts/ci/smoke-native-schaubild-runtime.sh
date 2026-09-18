#!/usr/bin/env bash
set -euo pipefail

base_url="${1:?base URL is required}"
host_header="127.0.0.1:8765"
manifest_out="$(mktemp)"
render_out="$(mktemp)"
viewer_path_out="$(mktemp)"
trap 'rm -f "$manifest_out" "$render_out" "$viewer_path_out"' EXIT

for _ in $(seq 1 30); do
  if curl --fail --silent \
    --header "Host: $host_header" \
    "$base_url/manifest.json" \
    --output "$manifest_out"; then
    break
  fi
  sleep 1
done

python - "$manifest_out" <<'PY'
import json
import sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text())
assert manifest["schema_version"] == "schauwerk-standalone-editor-manifest.v2"
assert manifest["editor_engine"] == "schauwerk-native-diagram-v1"
assert manifest["native_renderer"]["api_path"] == "/schaubild/api/native-viewer"
assert manifest["native_renderer"]["public_base_path"] == "/schaubild"
PY

curl --fail --silent \
  --header "Host: $host_header" \
  --header 'Content-Type: application/json' \
  --data-binary @docs/operators/fixtures/golden/decision-flow-v1.json \
  "$base_url/api/native-viewer" \
  --output "$render_out"

python - "$render_out" "$viewer_path_out" <<'PY'
import json
import sys
from pathlib import Path
result = json.loads(Path(sys.argv[1]).read_text())
assert result["renderer"] == "schauwerk-native-diagram-v1"
assert result["url"] == f"/schaubild/native/{result['input_digest']}/index.html"
Path(sys.argv[2]).write_text(
    result["url"].removeprefix("/schaubild"),
    encoding="utf-8",
)
PY

curl --fail --silent \
  --header "Host: $host_header" \
  "$base_url$(cat "$viewer_path_out")" \
  | grep -q 'id="nativeViewport"'
