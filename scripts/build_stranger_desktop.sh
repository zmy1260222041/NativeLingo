#!/usr/bin/env bash
# Reproducible Desktop Beta release build for Stranger (Windows x64 + macOS arm64).
#
# Reuses the Web Beta pipeline discipline:
#   1. exact Godot 4.6.3-stable version check;
#   2. --import + eight test suites (existing seven + DesktopBetaNoVoice);
#   3. export "Windows Desktop Beta" and "macOS Desktop Beta";
#   4. thin the macOS universal template binary to arm64;
#   5. sign macOS (Developer ID if configured, ad-hoc otherwise);
#   6. package Windows ZIP + macOS DMG;
#   7. SHA256SUMS.txt + build-info.json + 300 MiB package gate.
#
# Optional signing env:
#   MACOS_SIGN_IDENTITY  "Developer ID Application: ..."
#   APPLE_ID / APPLE_APP_PASSWORD / APPLE_TEAM_ID  -> notarize + staple
#
# Usage:
#   scripts/build_stranger_desktop.sh
#   SKIP_TESTS=1 scripts/build_stranger_desktop.sh
#   GODOT=/path/to/Godot scripts/build_stranger_desktop.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GAME_DIR="$ROOT/game"
OUT_DIR="$ROOT/build/desktop"
WIN_DIR="$OUT_DIR/windows"
MAC_DIR="$OUT_DIR/macos"
GODOT="${GODOT:-/Applications/Godot-4.6.app/Contents/MacOS/Godot}"
REQUIRED_VERSION_PREFIX="4.6.3.stable.official"
PACKAGE_BUDGET_MIB=300
LABEL="${DESKTOP_BUILD_LABEL:-desktop-beta.1}"

log() { printf '\033[1;36m[desktop-beta]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[desktop-beta] FAIL:\033[0m %s\n' "$*" >&2; exit 1; }

[[ -x "$GODOT" ]] || fail "Godot binary not found at $GODOT (set GODOT=/path/to/Godot)"
VERSION="$("$GODOT" --version 2>/dev/null || true)"
log "Godot version: ${VERSION:-unknown}"
[[ "$VERSION" == "$REQUIRED_VERSION_PREFIX"* ]] || fail "expected $REQUIRED_VERSION_PREFIX*, got ${VERSION:-unknown}"

TEST_HOME="${TEST_HOME:-$(mktemp -d -t stranger_desktop_home.XXXXXX)}"
cleanup() {
  if [[ -z "${TEST_HOME_KEEP:-}" ]]; then
    rm -rf "$TEST_HOME"
  fi
  if [[ -n "${DMG_STAGE:-}" ]]; then
    rm -rf "$DMG_STAGE"
  fi
}
trap cleanup EXIT

run_godot_test() {
  HOME="$TEST_HOME" "$GODOT" --headless --path "$GAME_DIR" "$@"
}

run_godot_export() {
  "$GODOT" --headless --path "$GAME_DIR" "$@"
}

expect_pass() {
  local label="$1"; shift
  local log_file
  log_file="$(mktemp -t stranger_desktop_test.XXXXXX)"
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
# 1. Import + tests.
# ---------------------------------------------------------------------------
log "importing project"
run_godot_test --import >/dev/null 2>&1 || fail "godot --import failed"

if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
  log "running tests"
  expect_pass "game-state smoke" --script res://tests/test_game_state.gd
  expect_pass "HUD smoke" res://tests/HudTest.tscn
  expect_pass "web-beta no-voice" res://tests/WebBetaNoVoiceTest.tscn
  expect_pass "desktop-beta no-voice" res://tests/DesktopBetaNoVoiceTest.tscn
  expect_pass "voice target cancel" res://tests/VoiceTargetCancelTest.tscn
  expect_pass "main env integration" res://tests/MainEnvIntegration.tscn
  expect_pass "walk animation safety" --script res://tests/test_walk_fix.gd
  expect_pass "directional locomotion" --script res://tests/test_directional_locomotion.gd
else
  log "SKIP_TESTS=1: skipping test phase"
fi

# ---------------------------------------------------------------------------
# 2. Export both desktop targets.
# ---------------------------------------------------------------------------
log "exporting desktop builds"
rm -rf "$WIN_DIR" "$MAC_DIR"
mkdir -p "$WIN_DIR" "$MAC_DIR"

run_godot_export --export-release "Windows Desktop Beta" "$WIN_DIR/stranger.exe" \
  | grep -viE 'save editor settings|editor_settings' || true
[[ -f "$WIN_DIR/stranger.exe" ]] || fail "Windows export did not produce stranger.exe"

run_godot_export --export-release "macOS Desktop Beta" "$MAC_DIR/Stranger.app" \
  | grep -viE 'save editor settings|editor_settings' || true
[[ -d "$MAC_DIR/Stranger.app" ]] || fail "macOS export did not produce Stranger.app"

# Official 4.6.3 macOS templates ship only a universal engine binary.
# User decision D4 is Apple Silicon only, so thin the exported binary.
APP_BIN="$MAC_DIR/Stranger.app/Contents/MacOS/Stranger"
if ! lipo -info "$APP_BIN" 2>/dev/null | grep -q 'Non-fat.*arm64'; then
  log "thinning macOS binary to arm64"
  lipo "$APP_BIN" -thin arm64 -output "$APP_BIN.arm64"
  mv "$APP_BIN.arm64" "$APP_BIN"
fi

# ---------------------------------------------------------------------------
# 3. Verify the macOS pck carries no development-only directories.
# ---------------------------------------------------------------------------
python3 - "$MAC_DIR/Stranger.app/Contents/Resources/Stranger.pck" <<'PY'
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
    print(f"  macOS pck entries checked: {count}")
PY

# ---------------------------------------------------------------------------
# 4. macOS signing + notarization (configurable), then packages.
# ---------------------------------------------------------------------------
MAC_SIGN_IDENTITY="${MACOS_SIGN_IDENTITY:-}"
if [[ -n "$MAC_SIGN_IDENTITY" ]]; then
  log "signing macOS app with $MAC_SIGN_IDENTITY"
  codesign --force --deep --options runtime --timestamp \
    --sign "$MAC_SIGN_IDENTITY" "$MAC_DIR/Stranger.app"
else
  log "no MACOS_SIGN_IDENTITY set; ad-hoc signing"
  codesign --force --deep --sign - "$MAC_DIR/Stranger.app"
fi

if [[ -n "${APPLE_ID:-}" && -n "${APPLE_APP_PASSWORD:-}" && -n "${APPLE_TEAM_ID:-}" ]]; then
  log "submitting macOS app for notarization"
  NOTARY_ZIP="$OUT_DIR/Stranger-notary.zip"
  ditto -c -k --keepParent "$MAC_DIR/Stranger.app" "$NOTARY_ZIP"
  xcrun notarytool submit "$NOTARY_ZIP" \
    --apple-id "$APPLE_ID" --password "$APPLE_APP_PASSWORD" --team-id "$APPLE_TEAM_ID" --wait
  xcrun stapler staple "$MAC_DIR/Stranger.app"
  rm -f "$NOTARY_ZIP"
  log "notarization complete"
fi

log "packaging Windows ZIP"
WIN_ZIP="$OUT_DIR/stranger-${LABEL}-windows-x64.zip"
rm -f "$WIN_ZIP"
( cd "$WIN_DIR" && zip -q -r -X "$WIN_ZIP" stranger.exe )

log "packaging macOS DMG"
DMG_STAGE="$OUT_DIR/dmg-stage"
rm -rf "$DMG_STAGE"; mkdir -p "$DMG_STAGE"
cp -R "$MAC_DIR/Stranger.app" "$DMG_STAGE/"
MAC_DMG="$OUT_DIR/stranger-${LABEL}-macos-arm64.dmg"
rm -f "$MAC_DMG"
hdiutil create -volname "Stranger ${LABEL}" -srcfolder "$DMG_STAGE" \
  -ov -format UDZO "$MAC_DMG" >/dev/null
rm -rf "$DMG_STAGE"

# ---------------------------------------------------------------------------
# 5. Checksums + metadata + size gate.
# ---------------------------------------------------------------------------
log "writing SHA256SUMS.txt"
(
  cd "$OUT_DIR"
  shasum -a 256 stranger-*.zip stranger-*.dmg > SHA256SUMS.txt
)

WIN_BYTES=$(wc -c < "$WIN_ZIP" | awk '{print $1}')
MAC_BYTES=$(wc -c < "$MAC_DMG" | awk '{print $1}')
WIN_MIB=$(awk -v b="$WIN_BYTES" 'BEGIN { printf "%.1f", b/1048576 }')
MAC_MIB=$(awk -v b="$MAC_BYTES" 'BEGIN { printf "%.1f", b/1048576 }')

BUILD_ID="${LABEL}-$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo local)"
python3 - "$OUT_DIR" "$BUILD_ID" "$VERSION" "$LABEL" "$WIN_ZIP" "$MAC_DMG" <<'PY'
import json, os, sys
out, build_id, version, label, win_zip, mac_dmg = sys.argv[1:7]
files = {}
for name in os.listdir(out):
    full = os.path.join(out, name)
    if os.path.isfile(full):
        files[name] = os.path.getsize(full)
payload = {
    "build_id": build_id,
    "build_label": label,
    "godot_version": version,
    "custom_features": ["desktop_beta_no_voice"],
    "targets": ["windows-x64", "macos-arm64"],
    "windows_zip": os.path.basename(win_zip),
    "macos_dmg": os.path.basename(mac_dmg),
    "files": files,
}
with open(os.path.join(out, "build-info.json"), "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, sort_keys=True)
    f.write("\n")
PY

log "Windows ZIP: ${WIN_MIB} MiB (budget ${PACKAGE_BUDGET_MIB} MiB)"
log "macOS DMG:  ${MAC_MIB} MiB (budget ${PACKAGE_BUDGET_MIB} MiB)"
for size_mib in "$WIN_MIB" "$MAC_MIB"; do
  if awk -v a="$size_mib" -v b="$PACKAGE_BUDGET_MIB" 'BEGIN { exit !(a > b) }'; then
    fail "package exceeds ${PACKAGE_BUDGET_MIB} MiB"
  fi
done

log "build complete: $OUT_DIR"
log "build id: $BUILD_ID"
log "artifacts:"
ls -lh "$WIN_ZIP" "$MAC_DMG" "$OUT_DIR/SHA256SUMS.txt" "$OUT_DIR/build-info.json"
