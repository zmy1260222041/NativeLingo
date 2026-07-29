#!/usr/bin/env bash
# Build a distributable NativeLingo .dmg.
#
# Phases (each aborts on error):
#   A  freeze the Python backend (PyInstaller --onedir) in a clean .venv-freeze
#   B  stage the onedir into src-tauri/resources/
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
#   * NONE for an unsigned GitHub build — video/audio decode uses PyAV (av),
#     whose wheels bundle the libav* libs (LGPL); no external ffmpeg needed.
#   * for D/F: Apple Developer ID Application cert in Keychain
#              ($DEVELOPER_ID_APPLICATION="Developer ID Application: Name (TEAMID)")
#              + `xcrun notarytool store-credentials AC_PROFILE ...` run once
#              ($NOTARY_KEYCHAIN_PROFILE="AC_PROFILE")
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MAC="$ROOT/desktop"   # macOS app source lives under desktop/ (shared assets stay at root)

FREEZE_VENV="$ROOT/.venv-freeze"
PYI_DIST="$ROOT/build/pyinstaller"
RES_DIR="$MAC/src-tauri/resources"
BUNDLE_MACOS="$MAC/src-tauri/target/release/bundle/macos"
APP_BUNDLE="$BUNDLE_MACOS/NativeLingo.app"
DMG_DIR="$MAC/src-tauri/target/release/bundle/dmg"

log() { printf "\n\033[1m=== %s ===\033[0m\n" "$*"; }
die() { printf "\033[31m[build_dmg] %s\033[0m\n" "$*" >&2; exit 1; }

# ── ensure Whisper base.en is staged for offline bundling ─────────────────
# transcribe.py loads ../../models/whisper-base.en if present (offline, no
# 141MB first-run download). Copy it from the HF cache if not already staged.
if [[ ! -d "$ROOT/models/whisper-base.en" ]]; then
    SNAP=$(ls -d "$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-base.en/snapshots/"*/ 2>/dev/null | head -1)
    if [[ -z "$SNAP" ]]; then
        die "models/whisper-base.en missing and not in HF cache. Run the dev app once to download base.en, then rebuild."
    fi
    mkdir -p "$ROOT/models"
    cp -RL "$SNAP" "$ROOT/models/whisper-base.en"
fi

# ── Phase A: freeze the backend ───────────────────────────────────────────
log "A: freeze backend (PyInstaller --onedir) in .venv-freeze"
if [[ ! -x "$FREEZE_VENV/bin/python" ]]; then
    python3 -m venv "$FREEZE_VENV"
    "$FREEZE_VENV/bin/pip" install --upgrade pip >/dev/null
fi
"$FREEZE_VENV/bin/pip" install -q -r "$MAC/requirements-runtime.txt" pyinstaller
"$FREEZE_VENV/bin/pyinstaller" "$MAC/backend/freeze.spec" --noconfirm \
    --distpath "$PYI_DIST" --workpath "$ROOT/build/pyinstaller_work"
[[ -x "$PYI_DIST/nativeLingoBackend/nativeLingoBackend" ]] \
    || die "freeze produced no binary"

# ── Phase B: stage sidecar into Tauri resources ───────────────────────────
log "B: stage onedir into src-tauri/resources/"
rm -rf "$RES_DIR/nativeLingoBackend"
cp -R "$PYI_DIST/nativeLingoBackend" "$RES_DIR/nativeLingoBackend"
# NOTE: do NOT strip the libs. strip -x leaves "Invalid Page" code signatures
# on some .dylib; on a clean Mac (no system copy to dlopen by name) the bundled
# lib is loaded and dyld rejects it → silent CODESIGNING crash at startup. The
# ~100MB saving isn't worth a broken-on-clean-Mac build.

# ── Phase C: Tauri build (.app only) ──────────────────────────────────────
log "C: npx tauri build --bundles app"
(cd "$MAC" && npx tauri build --bundles app)
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
    # Re-sign every native file first (some .so/.dylib carry a PyInstaller sig
    # that --deep doesn't refresh; per-file --force ensures all are valid), then
    # the outer app. arm64 refuses to load totally-unsigned/invalid-sig libs;
    # this lets downloaders run after the one-time Gatekeeper bypass
    # (right-click → Open). Notarization ($99/yr) is only for zero-friction
    # double-click — optional, later.
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
VERSION=$(grep -oE '"version": "[^"]+"' "$MAC/src-tauri/tauri.conf.json" | head -1 | cut -d'"' -f4)
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
