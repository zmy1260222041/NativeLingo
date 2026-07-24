#!/usr/bin/env bash
# Build a distributable NativeLingo .dmg.
#
# Phases (each aborts on error):
#   A  freeze the Python backend (PyInstaller --onedir) in a clean .venv-freeze
#   B  stage the onedir + bundled ffmpeg into src-tauri/resources/
#   C  npx tauri build --bundles app   ->  .app  (unsigned)
#   D  codesign the .app (Developer ID Application)   (only if $DEVELOPER_ID_APPLICATION)
#   E  create the .dmg via hdiutil (Tauri's own dmg step times out on the
#      ~1.4GB bundle via its AppleScript layout, so we make it ourselves)
#   F  notarize + staple the .dmg                     (only if $NOTARY_KEYCHAIN_PROFILE)
#
# Signing must precede dmg wrap (D before E): you sign the .app, then wrap the
# signed app into a dmg, then notarize the dmg.
#
# Prerequisites the script CANNOT set up for you (it checks and bails clearly):
#   * static arm64 ffmpeg + ffprobe in src-tauri/resources/bin/  (for /videos/process)
#       e.g. from https://evermeet.cx/ffmpeg/  (LGPL/GPL — confirm distribution license)
#   * for D/F: Apple Developer ID Application cert in Keychain
#              ($DEVELOPER_ID_APPLICATION="Developer ID Application: Name (TEAMID)")
#              + `xcrun notarytool store-credentials AC_PROFILE ...` run once
#              ($NOTARY_KEYCHAIN_PROFILE="AC_PROFILE")
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FREEZE_VENV="$ROOT/.venv-freeze"
PYI_DIST="$ROOT/build/pyinstaller"
RES_DIR="$ROOT/src-tauri/resources"
BUNDLE_MACOS="$ROOT/src-tauri/target/release/bundle/macos"
APP_BUNDLE="$BUNDLE_MACOS/NativeLingo.app"
DMG_DIR="$ROOT/src-tauri/target/release/bundle/dmg"

log() { printf "\n\033[1m=== %s ===\033[0m\n" "$*"; }
die() { printf "\033[31m[build_dmg] %s\033[0m\n" "$*" >&2; exit 1; }

# ── prerequisite: bundled ffmpeg ──────────────────────────────────────────
if [[ ! -x "$RES_DIR/bin/ffmpeg" || ! -x "$RES_DIR/bin/ffprobe" ]]; then
    die "missing src-tauri/resources/bin/ffmpeg or ffprobe. Download static arm64
binaries (e.g. https://evermeet.cx/ffmpeg/) and place them there before building.
(/analyze + /analyze_video work without it; /videos/process needs it.)"
fi

# ── Phase A: freeze the backend ───────────────────────────────────────────
log "A: freeze backend (PyInstaller --onedir) in .venv-freeze"
if [[ ! -x "$FREEZE_VENV/bin/python" ]]; then
    python3 -m venv "$FREEZE_VENV"
    "$FREEZE_VENV/bin/pip" install --upgrade pip >/dev/null
fi
"$FREEZE_VENV/bin/pip" install -q -r requirements-runtime.txt pyinstaller
"$FREEZE_VENV/bin/pyinstaller" backend/freeze.spec --noconfirm \
    --distpath "$PYI_DIST" --workpath "$ROOT/build/pyinstaller_work"
[[ -x "$PYI_DIST/nativeLingoBackend/nativeLingoBackend" ]] \
    || die "freeze produced no binary"

# ── Phase B: stage sidecar + ffmpeg into Tauri resources ──────────────────
log "B: stage onedir + ffmpeg into src-tauri/resources/"
rm -rf "$RES_DIR/nativeLingoBackend"
cp -R "$PYI_DIST/nativeLingoBackend" "$RES_DIR/nativeLingoBackend"
# strip local symbols from native libs (~100MB off; must precede codesign).
# strip -x only removes the local symbol table — code is untouched, safe.
find "$RES_DIR/nativeLingoBackend" -type f \( -name "*.dylib" -o -name "*.so" \) \
    -exec strip -x {} \; 2>/dev/null || true

# ── Phase C: Tauri build (.app only) ──────────────────────────────────────
log "C: npx tauri build --bundles app"
npx tauri build --bundles app
[[ -d "$APP_BUNDLE" ]] || die "tauri build produced no .app"

# ── Phase D: codesign the .app (optional, before dmg wrap) ────────────────
if [[ -n "${DEVELOPER_ID_APPLICATION:-}" ]]; then
    log "D: codesign .app (Developer ID Application, Hardened Runtime)"
    # Sign the PyInstaller tree deeply first (innermost dylibs/.so), then the app.
    find "$RES_DIR/nativeLingoBackend" -type f \
        \( -name "*.so" -o -name "*.dylib" -o -name "nativeLingoBackend" \) \
        -exec codesign --force --options runtime --timestamp \
            --sign "$DEVELOPER_ID_APPLICATION" {} \;
    codesign --force --deep --options runtime --timestamp \
        --sign "$DEVELOPER_ID_APPLICATION" "$APP_BUNDLE"
    codesign --verify --deep --strict "$APP_BUNDLE" || die "codesign verify failed"
else
    # No Developer ID: ad-hoc sign so the .app has a consistent signature.
    # strip (phase B) invalidated the PyInstaller libs' signatures, and
    # `codesign --deep` alone misses many nested .so/.dylib in the onedir
    # tree (→ arm64 kills the process on load). Re-sign every native file
    # first, then the outer app. arm64 refuses totally-unsigned binaries;
    # this ad-hoc sig lets downloaders run after the one-time Gatekeeper
    # bypass (right-click → Open). Notarization ($99/yr) is only for
    # zero-friction double-click — optional, later.
    log "D: ad-hoc sign (no Developer ID — GitHub-release ready)"
    find "$RES_DIR/nativeLingoBackend" -type f \
        \( -name "*.so" -o -name "*.dylib" -o -name "nativeLingoBackend" \) \
        -exec codesign --force --sign - {} \;
    codesign --force --deep --sign - "$APP_BUNDLE"
    codesign --verify --deep --strict "$APP_BUNDLE" || die "ad-hoc codesign verify failed"
fi

# ── Phase E: create the .dmg via hdiutil ──────────────────────────────────
# Image ONLY the .app from a clean staging dir: bundle/macos can contain
# Tauri's leftover read-write images (rw.*.dmg) from failed dmg attempts,
# which would otherwise bloat the source ~3x. ULFO (LZMA) >> UDZO (zlib) here.
log "E: create .dmg (hdiutil ULFO, clean staging)"
rm -f "$BUNDLE_MACOS"/rw.*.dmg 2>/dev/null || true
VERSION=$(grep -oE '"version": "[^"]+"' src-tauri/tauri.conf.json | head -1 | cut -d'"' -f4)
DMG="$DMG_DIR/NativeLingo_${VERSION}_aarch64.dmg"
mkdir -p "$DMG_DIR"
rm -f "$DMG"
STAGE=$(mktemp -d)
cp -R "$APP_BUNDLE" "$STAGE"/
hdiutil create -volname "NativeLingo" -srcfolder "$STAGE" -ov -format ULFO "$DMG"
rm -rf "$STAGE"
[[ -f "$DMG" ]] || die "hdiutil produced no dmg"

# ── Phase F: notarize + staple (optional) ─────────────────────────────────
if [[ -n "${NOTARY_KEYCHAIN_PROFILE:-}" ]]; then
    [[ -n "${DEVELOPER_ID_APPLICATION:-}" ]] \
        || die "notarization requires signing too (set DEVELOPER_ID_APPLICATION)"
    log "F: notarize + staple .dmg"
    xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_KEYCHAIN_PROFILE" --wait
    xcrun stapler staple "$DMG"
    xcrun stapler validate "$DMG" || die "stapler validate failed"
    echo "[build_dmg] notarized + stapled: $DMG"
else
    log "F: skipped (NOTARY_KEYCHAIN_PROFILE not set) — not notarized"
fi

log "done"
ls -lh "$DMG"
