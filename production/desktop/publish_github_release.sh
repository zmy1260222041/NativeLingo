#!/usr/bin/env bash
# Publish Stranger desktop artifacts to GitHub Releases as a DRAFT.
#
# Prerequisites:
#   gh CLI installed and authenticated (gh auth login), or GH_TOKEN set.
#   scripts/build_stranger_desktop.sh has produced build/desktop/.
#
# Env:
#   DESKTOP_TAG    release tag, default desktop-beta.1
#   GITHUB_REPO    default zmy1260222041/NativeLingo
#   DESKTOP_TITLE  optional release title
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="$ROOT/build/desktop"
NOTES="$ROOT/production/desktop/release_notes.md"
TAG="${DESKTOP_TAG:-desktop-beta.1}"
REPO="${GITHUB_REPO:-zmy1260222041/NativeLingo}"
TITLE="${DESKTOP_TITLE:-Stranger Desktop Beta $TAG}"

[[ -x "$(command -v gh)" ]] || { echo "install GitHub CLI (gh)" >&2; exit 1; }
[[ -f "$OUT_DIR/SHA256SUMS.txt" ]] || { echo "run scripts/build_stranger_desktop.sh first" >&2; exit 1; }

ZIP="$(find "$OUT_DIR" -maxdepth 1 -name 'stranger-*-windows-x64.zip' | head -1)"
DMG="$(find "$OUT_DIR" -maxdepth 1 -name 'stranger-*-macos-arm64.dmg' | head -1)"
[[ -n "$ZIP" && -n "$DMG" ]] || { echo "desktop artifacts missing" >&2; exit 1; }

# Keep the placeholder visible while the release remains a draft.
NOTES_TMP="$(mktemp -t stranger_desktop_release_notes.XXXXXX.md)"
sed 's|<问卷链接待回填>|问卷链接待回填（本 release 保持 draft）|g' "$NOTES" > "$NOTES_TMP"

echo "creating draft release $REPO tag=$TAG"
gh release create "$TAG" \
  --repo "$REPO" \
  --title "$TITLE" \
  --notes-file "$NOTES_TMP" \
  --draft \
  "$ZIP" "$DMG" "$OUT_DIR/SHA256SUMS.txt" "$OUT_DIR/build-info.json"

rm -f "$NOTES_TMP"
echo "draft created; review it on:"
echo "https://github.com/$REPO/releases/tag/$TAG"
