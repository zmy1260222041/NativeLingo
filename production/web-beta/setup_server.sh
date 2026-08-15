#!/usr/bin/env bash
# First-time server setup for the Stranger Web Beta (Tencent Cloud Ubuntu LTS).
# Run from the development machine. Requires DNS beta.<domain> to already point
# at the server and an SSH key with sudo rights on the server.
#
# Required env:
#   WEB_BETA_HOST=admin@<server-ip>
#   WEB_BETA_DOMAIN=<registered-domain>
#   WEB_BETA_EMAIL=<contact-email>        (certbot expiry notices)
# Optional:
#   WEB_BETA_KEY=/path/to/ssh/key
#   WEB_BETA_SSH_PORT=22
#
# This script does NOT configure the SSH admin-IP allowlist (that must be done
# in the Tencent firewall / security group or sshd_config with YOUR public IP,
# never a guess) and does NOT create tester accounts (see accounts.sh).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMPLATE="$ROOT/production/web-beta/nginx-site.conf.template"
HOST="${WEB_BETA_HOST:-}"
DOMAIN="${WEB_BETA_DOMAIN:-}"
EMAIL="${WEB_BETA_EMAIL:-}"
SSH_PORT="${WEB_BETA_SSH_PORT:-22}"
SSH_OPTS=(-p "$SSH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
[[ -n "${WEB_BETA_KEY:-}" ]] && SSH_OPTS+=(-i "$WEB_BETA_KEY")

[[ -n "$HOST" && -n "$DOMAIN" && -n "$EMAIL" ]] || {
  echo "required: WEB_BETA_HOST, WEB_BETA_DOMAIN, WEB_BETA_EMAIL" >&2
  exit 1
}

SITE_BASENAME="nativelingo-web-beta"
TMP_DIR="$(mktemp -d -t stranger_web_beta_server.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

sed "s/\${DOMAIN}/${DOMAIN}/g" "$TEMPLATE" > "$TMP_DIR/$SITE_BASENAME"
sed "s/\${DOMAIN}/${DOMAIN}/g" "$ROOT/production/web-beta/nginx-logrotate.conf.template" > "$TMP_DIR/nativelingo"

echo "uploading configs to $HOST"
scp "${SSH_OPTS[@]}" "$TMP_DIR/$SITE_BASENAME" "$HOST:/tmp/$SITE_BASENAME"
scp "${SSH_OPTS[@]}" "$TMP_DIR/nativelingo" "$HOST:/tmp/nativelingo-logrotate"

ssh "${SSH_OPTS[@]}" "$HOST" "DOMAIN='$DOMAIN' EMAIL='$EMAIL' bash -s" <<'REMOTE'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

sudo apt-get update -qq
sudo apt-get install -y -qq nginx certbot apache2-utils rsync python3 >/dev/null

# DNS must already resolve here. Standalone validation needs port 80 free.
sudo systemctl stop nginx || true
sudo mkdir -p /var/www/letsencrypt /srv/nativelingo/releases
if [[ ! -d "/etc/letsencrypt/live/beta.$DOMAIN" ]]; then
  sudo certbot certonly --standalone --non-interactive --agree-tos \
    -m "$EMAIL" -d "beta.$DOMAIN"
fi

sudo cp "/tmp/$SITE_BASENAME" "/etc/nginx/sites-available/$SITE_BASENAME"
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sfn "/etc/nginx/sites-available/$SITE_BASENAME" "/etc/nginx/sites-enabled/$SITE_BASENAME"

sudo cp /tmp/nativelingo-logrotate /etc/logrotate.d/nativelingo
sudo chmod 644 /etc/logrotate.d/nativelingo

sudo nginx -t
sudo systemctl enable --now nginx

# Certbot's systemd renewal timer keeps TLS valid; HTTP-01 renewals use the
# /.well-known/acme-challenge/ location in the site config.
sudo certbot renew --dry-run || true

echo "server setup complete for beta.$DOMAIN"
echo "next: restrict SSH to your admin IP, then run accounts.sh add tester01"
REMOTE
