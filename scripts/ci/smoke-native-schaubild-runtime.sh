#!/usr/bin/env bash
set -euo pipefail

base_url="${1:?base URL is required}"
host_header="127.0.0.1:8765"
manifest_out="$(mktemp)"
render_out="$(mktemp)"
viewer_path_out="$(mktemp)"
viewer_manifest_out="$(mktemp)"
trap 'rm -f "$manifest_out" "$render_out" "$viewer_path_out" "$viewer_manifest_out"' EXIT

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
  --header 'X-Forwarded-For: 127.0.0.1' \
  --header 'Content-Type: application/json' \
  --data-binary @docs/operators/fixtures/golden/decision-flow-v1.json \
  "$base_url/api/native-viewer" \
  --output "$render_out"

prefixed_status="$(
  curl --silent --output /dev/null --write-out '%{http_code}' \
    --header "Host: $host_header" \
    --header 'X-Forwarded-For: 127.0.0.1' \
    --header 'Content-Type: application/json' \
    --data-binary @docs/operators/fixtures/golden/decision-flow-v1.json \
    "$base_url/schaubild/api/native-viewer"
)"
test "$prefixed_status" = "404"

python - "$render_out" "$viewer_path_out" <<'PY'
import json
import re
import sys
from pathlib import Path
result = json.loads(Path(sys.argv[1]).read_text())
assert result["renderer"] == "schauwerk-native-diagram-v1"
assert re.fullmatch(r"/schaubild/native/[0-9a-f]{32}/index\.html", result["url"])
Path(sys.argv[2]).write_text(
    result["url"].removeprefix("/schaubild"),
    encoding="utf-8",
)
PY

curl --fail --silent \
  --header "Host: $host_header" \
  --header 'X-Forwarded-For: 127.0.0.1' \
  "$base_url$(cat "$viewer_path_out")" \
  | grep -q 'id="nativeViewport"'

viewer_manifest_path="$(sed 's/index\.html$/manifest.json/' "$viewer_path_out")"
curl --fail --silent \
  --header "Host: $host_header" \
  --header 'X-Forwarded-For: 127.0.0.1' \
  "$base_url$viewer_manifest_path" \
  --output "$viewer_manifest_out"

python - "$viewer_manifest_out" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
boundary = manifest["network_boundary"]
assert boundary["serve_binding"] == "trusted-reverse-proxy-private-ingress"
assert boundary["public_base_path"] == "/schaubild"
assert boundary["delivery"] == "integrated-schaubild-runtime"
assert "production-readiness" not in manifest["does_not_establish"]
PY
