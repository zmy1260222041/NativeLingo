#!/usr/bin/env bash
# Stranger Web Beta account management — runs ON THE SERVER only.
# Passwords are random, shown exactly once, and stored as bcrypt hashes in
# /srv/nativelingo/accounts.htpasswd. This file is never committed.
#
# Usage:
#   sudo ./accounts.sh add tester01      # create/replace account, prints password
#   sudo ./accounts.sh revoke tester01   # revoke immediately (nginx reload optional)
#   sudo ./accounts.sh list              # list aliases (no hashes)
#   sudo ./accounts.sh batch 2           # create internal smoke-test accounts

set -euo pipefail

ACCOUNTS_FILE="/srv/nativelingo/accounts.htpasswd"
ALIAS_RE='^[a-z0-9][a-z0-9_-]{2,31}$'
PASSWORD_CHARS='A-Za-z0-9!@#%^*-_=+'

require_root() { [[ "${EUID}" -eq 0 ]] || { echo "run as root" >&2; exit 1; }; }
require_htpasswd() { command -v htpasswd >/dev/null || { echo "install apache2-utils" >&2; exit 1; }; }

random_password() {
  LC_ALL=C tr -dc "${PASSWORD_CHARS}" </dev/urandom | head -c 24
}

valid_alias() { [[ "$1" =~ ${ALIAS_RE} ]]; }

reload_nginx() {
  if nginx -t -q 2>/dev/null; then
    systemctl reload nginx
  fi
}

cmd="${1:-}"; shift || true
case "$cmd" in
  add)
    require_root; require_htpasswd
    alias="${1:-}"
    [[ -z "$alias" ]] && { echo "usage: $0 add <alias>" >&2; exit 1; }
    valid_alias "$alias" || { echo "invalid alias (2-32 chars, a-z0-9_-)" >&2; exit 1; }
    mkdir -p "$(dirname "$ACCOUNTS_FILE")"
    touch "$ACCOUNTS_FILE"
    chmod 600 "$ACCOUNTS_FILE"
    password="$(random_password)"
    if htpasswd -B -C 10 -b "$ACCOUNTS_FILE" "$alias" "$password" >/dev/null 2>&1; then
      echo "account=$alias"
      echo "password=$password"
      echo "store this now; it will not be printed again."
      reload_nginx
    else
      echo "htpasswd failed (bcrypt support required)" >&2
      exit 1
    fi
    ;;
  revoke)
    require_root; require_htpasswd
    alias="${1:-}"
    [[ -z "$alias" ]] && { echo "usage: $0 revoke <alias>" >&2; exit 1; }
    if [[ -f "$ACCOUNTS_FILE" ]]; then
      htpasswd -D "$ACCOUNTS_FILE" "$alias" >/dev/null 2>&1 || true
      reload_nginx
      echo "revoked=$alias"
    fi
    ;;
  list)
    require_root
    if [[ -f "$ACCOUNTS_FILE" ]]; then
      cut -d: -f1 "$ACCOUNTS_FILE"
    fi
    ;;
  batch)
    require_root; require_htpasswd
    count="${1:-0}"
    [[ "$count" =~ ^[0-9]+$ ]] || { echo "usage: $0 batch <count>" >&2; exit 1; }
    for i in $(seq 1 "$count"); do
      alias="tester$(printf '%02d' "$i")"
      "$0" add "$alias"
    done
    ;;
  *)
    echo "usage: $0 {add|revoke|list|batch} ..." >&2
    exit 1
    ;;
esac
