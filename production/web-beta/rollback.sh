#!/usr/bin/env bash
# Instant rollback: point /srv/nativelingo/current back at the previous release.
# Usage: WEB_BETA_HOST=admin@1.2.3.4 production/web-beta/rollback.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${WEB_BETA_HOST:-}"
SSH_PORT="${WEB_BETA_SSH_PORT:-22}"
SSH_OPTS=(-p "$SSH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
[[ -n "${WEB_BETA_KEY:-}" ]] && SSH_OPTS+=(-i "$WEB_BETA_KEY")
[[ -n "$HOST" ]] || { echo "set WEB_BETA_HOST=admin@server" >&2; exit 1; }

ssh "${SSH_OPTS[@]}" "$HOST" bash -s <<'REMOTE'
set -euo pipefail
BASE=/srv/nativelingo
if [[ ! -e "$BASE/previous" ]]; then
  echo "no previous release to roll back to" >&2
  exit 1
fi
PREV="$(readlink -f "$BASE/previous")"
CURRENT="$(readlink -f "$BASE/current" || true)"
sudo ln -sfn "$PREV" "$BASE/current"
sudo nginx -t
sudo systemctl reload nginx
echo "rolled back to $(readlink -f "$BASE/current")"
echo "previous was $CURRENT"
REMOTE
