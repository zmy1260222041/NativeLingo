#!/usr/bin/env bash
# Reproducible Web Beta release build for the Stranger vertical slice.
#
# What it does:
#   1. Verifies the exact Godot editor version (4.6.3-stable).
#   2. Re-imports the project (regenerates .translation resources).
#   3. Runs the gameplay / HUD / web-no-voice test suites.
#   4. Exports the "Web Beta" preset (Compatibility, no threads, no PWA,
#      custom feature web_beta_no_voice) to build/web/.
#   5. Precompresses index.wasm / index.pck / index.js with gzip -9.
#   6. Emits SHA256SUMS + build-info.json and enforces the 70 MiB first-load gate.
#
# Usage:
#   scripts/build_stranger_web_beta.sh            # full build
#   SKIP_TESTS=1 scripts/build_stranger_web_beta.sh
#   GODOT=/path/to/Godot scripts/build_stranger_web_beta.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GAME_DIR="$ROOT/game"
OUT_DIR="$ROOT/build/web"
GODOT="${GODOT:-/Applications/Godot-4.6.app/Contents/MacOS/Godot}"
REQUIRED_VERSION_PREFIX="4.6.3.stable.official"
COMPRESSED_BUDGET_MIB=70

log() { printf '\033[1;36m[web-beta]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[web-beta] FAIL:\033[0m %s\n' "$*" >&2; exit 1; }

if [[ ! -x "$GODOT" ]]; then
  fail "Godot binary not found at $GODOT (set GODOT=/path/to/Godot)"
fi

VERSION="$("$GODOT" --version 2>/dev/null || true)"
log "Godot version: ${VERSION:-unknown}"
if [[ "$VERSION" != "$REQUIRED_VERSION_PREFIX"* ]]; then
  fail "expected $REQUIRED_VERSION_PREFIX*, got ${VERSION:-unknown}"
fi

TEST_HOME="${TEST_HOME:-$(mktemp -d -t stranger_web_beta_home.XXXXXX)}"
if [[ -z "${TEST_HOME_KEEP:-}" ]]; then
  trap 'rm -rf "$TEST_HOME"' EXIT
fi

run_godot_test() {
  # Headless test runs need a writable HOME: Godot's rotated logger creates
  # user://logs before the SceneTree is available and aborts if HOME is
  # unwritable. Export runs separately with the real HOME so the installed
  # export templates are found.
  HOME="$TEST_HOME" "$GODOT" --headless --path "$GAME_DIR" "$@"
}

run_godot_export() {
  "$GODOT" --headless --path "$GAME_DIR" "$@"
}

expect_pass() {
  local kind="$1"; shift
  local label="$1"; shift
  local log_file
  log_file="$(mktemp -t stranger_web_beta_test.XXXXXX)"
  if run_godot_test "$@" >"$log_file" 2>&1; then
    if grep -Eq 'PASS:|MAIN_ENV_INTEGRATION_PASS' "$log_file"; then
      log "test OK  $label"
      rm -f "$log_file"
      return 0
    fi
  fi
  tail -40 "$log_file" >&2
  fail "test failed: $label"
}

# ---------------------------------------------------------------------------
# 1. Import (idempotent; also regenerates CSV-derived translation resources).
# ---------------------------------------------------------------------------
log "importing project"
run_godot_test --import >/dev/null 2>&1 || fail "godot --import failed"

# ---------------------------------------------------------------------------
# 2. Tests. The web-no-voice suite is the launch-critical one.
# ---------------------------------------------------------------------------
if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
  log "running tests"
  expect_pass scene "game-state smoke" --script res://tests/test_game_state.gd
  expect_pass scene "HUD smoke" res://tests/HudTest.tscn
  expect_pass scene "web-beta no-voice" res://tests/WebBetaNoVoiceTest.tscn
  expect_pass scene "voice target cancel" res://tests/VoiceTargetCancelTest.tscn
  expect_pass scene "main env integration" res://tests/MainEnvIntegration.tscn
  expect_pass scene "walk animation safety" --script res://tests/test_walk_fix.gd
  expect_pass scene "directional locomotion" --script res://tests/test_directional_locomotion.gd
else
  log "SKIP_TESTS=1: skipping test phase"
fi

# ---------------------------------------------------------------------------
# 3. Export. The preset path is ../build/web relative to game/.
# ---------------------------------------------------------------------------
log "exporting Web Beta release"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
run_godot_export --export-release "Web Beta" "$OUT_DIR/index.html" \
  | grep -viE 'save editor settings|editor_settings' || true

if [[ ! -f "$OUT_DIR/index.html" || ! -f "$OUT_DIR/index.pck" || ! -f "$OUT_DIR/index.wasm" ]]; then
  fail "export did not produce index.html / index.pck / index.wasm"
fi

# ---------------------------------------------------------------------------
# 3b. Inject the pointer-lock patch into the generated HTML shell before the
# engine script tag (keeps Chrome console free of WrongDocumentError and lets
# the first trusted click acquire the pointer).
# ---------------------------------------------------------------------------
log "patching web shell (pointer lock + silent optional failure)"
python3 - "$OUT_DIR/index.html" "$ROOT/production/web-beta/web_shell_patch.js" <<'PY'
import pathlib, sys
html_path, patch_path = sys.argv[1], sys.argv[2]
html = pathlib.Path(html_path).read_text(encoding="utf-8")
patch = pathlib.Path(patch_path).read_text(encoding="utf-8")
marker = '<script src="index.js"></script>'
if marker not in html:
    raise SystemExit("index.html does not contain the engine script tag")
if "web-beta-pointer-lock-patch" in html:
    raise SystemExit("web shell already patched (re-export first)")
injection = f'<script id="web-beta-pointer-lock-patch">\n{patch}\n\t\t</script>\n\t\t'
html = html.replace(marker, injection + marker, 1)
pathlib.Path(html_path).write_text(html, encoding="utf-8")
print("  web shell patched")
PY

# ---------------------------------------------------------------------------
# 4. Verify the shipped PCK contains no development-only directories.
# ---------------------------------------------------------------------------
python3 - "$OUT_DIR/index.pck" <<'PY'
import struct, sys
path = sys.argv[1]
with open(path, "rb") as f:
    f.seek(32)
    dir_offset = struct.unpack("<Q", f.read(8))[0]
    f.seek(dir_offset)
    count = struct.unpack("<I", f.read(4))[0]
    banned = ("tests", "tools", "addons", "speech_service")
    bad = []
    for _ in range(count):
        length = struct.unpack("<I", f.read(4))[0]
        name = f.read(length).rstrip(b"\x00").decode("utf-8", "replace")
        f.read(16)  # offset + size
        f.read(16)  # md5
        f.read(4)   # flags
        if any(f"res://{token}" in name for token in banned):
            bad.append(name)
    if bad:
        for name in bad:
            print("  banned entry:", name, file=sys.stderr)
        raise SystemExit(1)
    print(f"  pck entries checked: {count}")
PY

# ---------------------------------------------------------------------------
# 5. Precompress + checksums + build metadata.
# ---------------------------------------------------------------------------
log "precompressing wasm/pck/js (gzip -9)"
gzip -9 -k -f "$OUT_DIR/index.wasm" "$OUT_DIR/index.pck" "$OUT_DIR/index.js"

log "writing SHA256SUMS"
(
  cd "$OUT_DIR"
  shasum -a 256 ./* > SHA256SUMS
)

COMPRESSED_BYTES=$(wc -c "$OUT_DIR/index.wasm.gz" "$OUT_DIR/index.pck.gz" "$OUT_DIR/index.js.gz" | tail -1 | awk '{print $1}')
COMPRESSED_MIB=$(awk -v b="$COMPRESSED_BYTES" 'BEGIN { printf "%.1f", b/1048576 }')

BUILD_ID="web-beta.1-$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo local)"
python3 - "$OUT_DIR" "$BUILD_ID" "$VERSION" "$COMPRESSED_BYTES" <<'PY'
import json, os, sys
out, build_id, version, compressed_bytes = sys.argv[1:5]
files = {}
for name in os.listdir(out):
    full = os.path.join(out, name)
    if os.path.isfile(full):
        files[name] = os.path.getsize(full)
payload = {
    "build_id": build_id,
    "build_label": "web-beta.1",
    "godot_version": version,
    "custom_features": ["web_beta_no_voice"],
    "threads": False,
    "pwa": False,
    "compressed_first_load_bytes": int(compressed_bytes),
    "files": files,
}
with open(os.path.join(out, "build-info.json"), "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, sort_keys=True)
    f.write("\n")
PY

log "first-load compressed payload: ${COMPRESSED_MIB} MiB (budget ${COMPRESSED_BUDGET_MIB} MiB)"
if awk -v a="$COMPRESSED_MIB" -v b="$COMPRESSED_BUDGET_MIB" 'BEGIN { exit !(a > b) }'; then
  fail "compressed first-load payload exceeds ${COMPRESSED_BUDGET_MIB} MiB"
fi

if [[ "${RUN_BROWSER_SMOKE:-0}" == "1" ]]; then
  log "browser smoke (WEB_BETA_HEADED=1 additionally asserts pointer lock)"
  node "$ROOT/production/web-beta/browser_smoke.mjs"
fi

log "build complete: $OUT_DIR"
log "build id: $BUILD_ID"
