#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SYSTEMD_DIR="$APP_DIR/deploy/systemd"
NGINX_DIR="$APP_DIR/deploy/nginx"
SMOKE_SCRIPT="$APP_DIR/deploy/smoke_check.sh"

DOMAIN="${DOMAIN:-presek.live}"
SERVER_USER="${SERVER_USER:-emiloffingen}"
APP_ROOT="${APP_ROOT:-/home/emiloffingen/presek}"
CERT_FULLCHAIN="${CERT_FULLCHAIN:-/etc/ssl/cloudflare/presek.live/fullchain.pem}"
CERT_PRIVKEY="${CERT_PRIVKEY:-/etc/ssl/cloudflare/presek.live/privkey.pem}"

SITE_NAME="$DOMAIN.conf"
SITE_AVAILABLE="/etc/nginx/sites-available/$SITE_NAME"
SITE_ENABLED="/etc/nginx/sites-enabled/$SITE_NAME"
REALIP_SNIPPET="/etc/nginx/snippets/cloudflare-realip.conf"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }
}

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "Run this script as root: sudo bash deploy/install_server.sh" >&2
    exit 1
  fi
}

replace_paths() {
  local src="$1"
  local dest="$2"

  sed \
    -e "s|/home/emiloffingen/presek|$APP_ROOT|g" \
    -e "s|User=emiloffingen|User=$SERVER_USER|g" \
    -e "s|/etc/ssl/cloudflare/presek.live/fullchain.pem|$CERT_FULLCHAIN|g" \
    -e "s|/etc/ssl/cloudflare/presek.live/privkey.pem|$CERT_PRIVKEY|g" \
    -e "s|server_name presek.live www.presek.live;|server_name $DOMAIN www.$DOMAIN;|g" \
    "$src" > "$dest"
}

main() {
  need_cmd systemctl
  need_cmd nginx
  need_cmd sed
  need_cmd curl
  require_root

  [ -d "$APP_ROOT/venv" ] || { echo "Missing Python virtualenv at $APP_ROOT/venv" >&2; exit 1; }
  [ -f "$APP_ROOT/web/dist/server/entry.mjs" ] || { echo "Missing Astro server build at $APP_ROOT/web/dist/server/entry.mjs" >&2; exit 1; }
  [ -f "$CERT_FULLCHAIN" ] || { echo "Missing TLS certificate at $CERT_FULLCHAIN" >&2; exit 1; }
  [ -f "$CERT_PRIVKEY" ] || { echo "Missing TLS private key at $CERT_PRIVKEY" >&2; exit 1; }

  install -d /etc/systemd/system
  install -d /etc/nginx/sites-available
  install -d /etc/nginx/sites-enabled
  install -d /etc/nginx/snippets

  for unit in presek.target presek-worker.service presek-beat.service presek-fastapi.service presek-astro.service; do
    replace_paths "$SYSTEMD_DIR/$unit" "/etc/systemd/system/$unit"
  done

  systemd-analyze verify /etc/systemd/system/presek.target /etc/systemd/system/presek-worker.service /etc/systemd/system/presek-beat.service /etc/systemd/system/presek-fastapi.service /etc/systemd/system/presek-astro.service

  replace_paths "$NGINX_DIR/presek.live.conf" "$SITE_AVAILABLE"
  cp "$NGINX_DIR/cloudflare-realip.conf" "$REALIP_SNIPPET"

  ln -sfn "$SITE_AVAILABLE" "$SITE_ENABLED"

  systemctl daemon-reload
  systemctl enable presek.target

  nginx -t
  systemctl restart nginx
  systemctl restart presek.target

  ENABLE_PUBLIC_CHECK=0 "$SMOKE_SCRIPT"

  echo ""
  echo "Deployment files installed."
  echo "Check services with:"
  echo "  sudo systemctl status presek.target"
  echo "  sudo journalctl -u presek-fastapi.service -f"
  echo "  sudo bash deploy/backup_postgres.sh"
}

main "$@"
