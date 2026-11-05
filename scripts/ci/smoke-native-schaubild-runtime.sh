#!/usr/bin/env bash
set -euo pipefail

base_url="${1:?base URL is required}"
host_header="127.0.0.1:8765"
manifest_out="$(mktemp)"
render_out="$(mktemp)"
viewer_path_out="$(mktemp)"
viewer_html_out="$(mktemp)"
viewer_manifest_out="$(mktemp)"
d2_caps_out="$(mktemp)"
d2_req_out="$(mktemp)"
d2_svg_out="$(mktemp)"
d2_headers_out="$(mktemp)"
trap 'rm -f "$manifest_out" "$render_out" "$viewer_path_out" "$viewer_html_out" "$viewer_manifest_out" "$d2_caps_out" "$d2_req_out" "$d2_svg_out" "$d2_headers_out"' EXIT

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
  --output "$viewer_html_out"
grep -q 'id="nativeViewport"' "$viewer_html_out"

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
# The native path above remains the default. Prove the opt-in D2 renderer is
# actually available and serves a source-bound passive SVG inside the image.
curl --fail --silent --show-error \
  --header "Host: $host_header" \
  --header 'X-Forwarded-For: 127.0.0.1' \
  "$base_url/api/renderer-capabilities" \
  --output "$d2_caps_out"

python - "$d2_caps_out" "$d2_req_out" <<'PY'
import json
import sys
from pathlib import Path

capabilities = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert capabilities["schema_version"] == "schauwerk-renderer-capabilities.v1"
assert len(capabilities["renderers"]) == 1
d2 = capabilities["renderers"][0]
assert d2["id"] == "d2-tala"
assert d2["read_only"] is True
assert {"process", "architecture"}.issubset(d2["supported_intents"])

source = json.loads(
    Path("docs/operators/fixtures/golden/decision-flow-v1.json").read_text(encoding="utf-8")
)
request = {
    "schema_version": "schauwerk-renderer-preview-request.v1",
    "renderer": "d2-tala",
    "representation": source,
}
Path(sys.argv[2]).write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
PY

curl --fail --silent --show-error \
  --header "Host: $host_header" \
  --header 'X-Forwarded-For: 127.0.0.1' \
  --header 'Content-Type: application/json' \
  --data-binary @"$d2_req_out" \
  --dump-header "$d2_headers_out" \
  "$base_url/api/d2-preview" \
  --output "$d2_svg_out"

python - "$d2_svg_out" "$d2_headers_out" <<'PY'
import hashlib
import re
import sys
from pathlib import Path
from xml.etree import ElementTree

svg = Path(sys.argv[1]).read_bytes()
headers = Path(sys.argv[2]).read_text(encoding="utf-8")
fields = {
    key.lower(): value.strip()
    for line in headers.splitlines()
    if ":" in line
    for key, value in [line.split(":", 1)]
}
root = ElementTree.fromstring(svg)
assert root.tag == "{http://www.w3.org/2000/svg}svg"
assert root.get("data-d2-version") == "v0.9.0"
assert fields["x-schauwerk-renderer"] == "d2-tala-v0.9.0"
assert re.fullmatch(r"[0-9a-f]{64}", fields["x-schauwerk-input-digest"])
assert fields["x-schauwerk-output-sha256"] == hashlib.sha256(svg).hexdigest()
texts = [
    "".join(element.itertext())
    for element in root.iter()
    if element.tag == "{http://www.w3.org/2000/svg}text"
]
assert any("Änderungswunsch" in text for text in texts)
assert any("Risiko vertretbar?" in text for text in texts)
PY
