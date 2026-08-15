#!/usr/bin/env bash
# Deploy a built web-beta release from the development machine to the Tencent
# Cloud server over SSH/rsync. No CI in the first release.
#
# Required environment:
#   WEB_BETA_HOST   admin@server-ip or ssh alias
#   WEB_BETA_KEY    optional: path to SSH private key
# Optional:
#   WEB_BETA_SSH_PORT   default 22
#
# Server layout:
#   /srv/nativelingo/releases/<build-id>/   immutable release
#   /srv/nativelingo/current -> releases/<build-id>
#   /srv/nativelingo/previous -> last release (for rollback)
#
# Usage:
#   scripts/build_stranger_web_beta.sh
#   WEB_BETA_HOST=admin@1.2.3.4 production/web-beta/deploy.sh
#   production/web-beta/rollback.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="$ROOT/build/web"
REMOTE_BASE="/srv/nativelingo"
HOST="${WEB_BETA_HOST:-}"
SSH_PORT="${WEB_BETA_SSH_PORT:-22}"
SSH_OPTS=(-p "$SSH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
[[ -n "${WEB_BETA_KEY:-}" ]] && SSH_OPTS+=(-i "$WEB_BETA_KEY")
RSYNC_OPTS=(-az --delete --chmod=Du=rwx,Dg=rx,Do=rx,Fu=rw,Fg=r,Fo=r)

[[ -n "$HOST" ]] || { echo "set WEB_BETA_HOST=admin@server" >&2; exit 1; }
[[ -f "$OUT_DIR/build-info.json" ]] || { echo "run scripts/build_stranger_web_beta.sh first" >&2; exit 1; }

BUILD_ID="$(python3 - "$OUT_DIR/build-info.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    print(json.load(f)["build_id"])
PY
)"

echo "deploying $BUILD_ID to $HOST"

ssh "${SSH_OPTS[@]}" "$HOST" "sudo mkdir -p $REMOTE_BASE/releases/$BUILD_ID"
rsync "${RSYNC_OPTS[@]}" -e "ssh ${SSH_OPTS[*]}" "$OUT_DIR/" "$HOST:$REMOTE_BASE/releases/$BUILD_ID/"

ssh "${SSH_OPTS[@]}" "$HOST" "BUILD_ID='$BUILD_ID' bash -s" <<'REMOTE'
set -euo pipefail
BASE=/srv/nativelingo
if [[ -e "$BASE/current" ]]; then
  OLD="$(readlink -f "$BASE/current" || true)"
  if [[ -n "$OLD" && "$OLD" != "$BASE/releases/$BUILD_ID" ]]; then
    sudo ln -sfn "$OLD" "$BASE/previous"
  fi
fi
sudo ln -sfn "$BASE/releases/$BUILD_ID" "$BASE/current"
sudo nginx -t
sudo systemctl reload nginx
echo "current -> $(readlink -f "$BASE/current")"
echo "previous -> $(readlink -f "$BASE/previous" 2>/dev/null || echo none)"
REMOTE

echo "deploy complete: $BUILD_ID"
echo "rollback command: production/web-beta/rollback.sh"
