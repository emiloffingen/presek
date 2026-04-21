#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SYSTEMD_DIR="$APP_DIR/deploy/systemd"
NGINX_DIR="$APP_DIR/deploy/nginx"
SMOKE_SCRIPT="$APP_DIR/deploy/smoke_check.sh"

DOMAIN="${DOMAIN:-presek.live}"
SERVER_USER="${SERVER_USER:-emiloffingen}"
APP_ROOT="${APP_ROOT:-/home/emiloffingen/presek-runtime}"
CERT_FULLCHAIN="${CERT_FULLCHAIN:-/etc/ssl/cloudflare/presek.live/fullchain.pem}"
CERT_PRIVKEY="${CERT_PRIVKEY:-/etc/ssl/cloudflare/presek.live/privkey.pem}"
INSTALL_NGINX="${INSTALL_NGINX:-auto}"
CURRENT_ROOT="$APP_ROOT/current"
SHARED_ROOT="$APP_ROOT/shared"
APP_SERVICES=(
  presek-fastapi.service
  presek-astro.service
  presek-worker.service
  presek-worker-ingestion.service
  presek-worker-delivery.service
  presek-beat.service
)

SITE_NAME="$DOMAIN.conf"
SITE_AVAILABLE="/etc/nginx/sites-available/$SITE_NAME"
SITE_ENABLED="/etc/nginx/sites-enabled/$SITE_NAME"
REALIP_SNIPPET="/etc/nginx/snippets/cloudflare-realip.conf"
SECURITY_SNIPPET="/etc/nginx/snippets/presek-security-headers.conf"
LEGACY_SITE_ENABLED="/etc/nginx/sites-enabled/presek"
LEGACY_SITE_AVAILABLE="/etc/nginx/sites-available/presek"
DISABLED_SITES_DIR="/etc/nginx/sites-disabled"

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
    -e "s|/home/emiloffingen/presek-runtime|$APP_ROOT|g" \
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
  [ -f "$SHARED_ROOT/.env" ] || { echo "Missing shared env file at $SHARED_ROOT/.env" >&2; exit 1; }
  [ -f "$CURRENT_ROOT/api_fast.py" ] || { echo "Missing current release at $CURRENT_ROOT" >&2; exit 1; }
  [ -f "$CURRENT_ROOT/web/dist/server/entry.mjs" ] || { echo "Missing Astro server build at $CURRENT_ROOT/web/dist/server/entry.mjs" >&2; exit 1; }

  if [ "$INSTALL_NGINX" = "auto" ]; then
    if [ -f "$CERT_FULLCHAIN" ] && [ -f "$CERT_PRIVKEY" ]; then
      INSTALL_NGINX=1
    else
      INSTALL_NGINX=nossl
    fi
  fi

  if [ "$INSTALL_NGINX" = "1" ]; then
    [ -f "$CERT_FULLCHAIN" ] || { echo "Missing TLS certificate at $CERT_FULLCHAIN" >&2; exit 1; }
    [ -f "$CERT_PRIVKEY" ] || { echo "Missing TLS private key at $CERT_PRIVKEY" >&2; exit 1; }
  fi

  install -d -o "$SERVER_USER" -g "$SERVER_USER" "$APP_ROOT"
  install -d -o "$SERVER_USER" -g "$SERVER_USER" "$APP_ROOT/releases"
  install -d -o "$SERVER_USER" -g "$SERVER_USER" "$SHARED_ROOT"
  install -d -o "$SERVER_USER" -g "$SERVER_USER" "$SHARED_ROOT/logs"
  install -d -o "$SERVER_USER" -g "$SERVER_USER" "$SHARED_ROOT/backups"
  install -d -o "$SERVER_USER" -g "$SERVER_USER" "$SHARED_ROOT/huggingface"
  install -d -o "$SERVER_USER" -g "$SERVER_USER" "$SHARED_ROOT/huggingface/hub"
  install -d -o "$SERVER_USER" -g "$SERVER_USER" "$SHARED_ROOT/huggingface/transformers"
  install -d -o "$SERVER_USER" -g "$SERVER_USER" "$SHARED_ROOT/huggingface/sentence_transformers"
  install -d /etc/systemd/system

  for unit in presek.target presek-worker.service presek-worker-ingestion.service presek-worker-delivery.service presek-beat.service presek-fastapi.service presek-astro.service; do
    replace_paths "$SYSTEMD_DIR/$unit" "/etc/systemd/system/$unit"
  done

  systemd-analyze verify /etc/systemd/system/presek.target /etc/systemd/system/presek-worker.service /etc/systemd/system/presek-worker-ingestion.service /etc/systemd/system/presek-worker-delivery.service /etc/systemd/system/presek-beat.service /etc/systemd/system/presek-fastapi.service /etc/systemd/system/presek-astro.service

  systemctl daemon-reload
  systemctl enable presek.target

  if [ "$INSTALL_NGINX" = "1" ] || [ "$INSTALL_NGINX" = "nossl" ]; then
    install -d /etc/nginx/sites-available
    install -d /etc/nginx/sites-enabled
    install -d "$DISABLED_SITES_DIR"
    install -d /etc/nginx/snippets

    if [ "$INSTALL_NGINX" = "nossl" ]; then
      replace_paths "$NGINX_DIR/presek.live.nossl.conf" "$SITE_AVAILABLE"
    else
      replace_paths "$NGINX_DIR/presek.live.conf" "$SITE_AVAILABLE"
    fi
    cp "$NGINX_DIR/cloudflare-realip.conf" "$REALIP_SNIPPET"
    cp "$NGINX_DIR/security-headers.conf" "$SECURITY_SNIPPET"
    ln -sfn "$SITE_AVAILABLE" "$SITE_ENABLED"

    if [ -e "$LEGACY_SITE_ENABLED" ] && grep -q "server_name .*presek.live" "$LEGACY_SITE_ENABLED"; then
      mv "$LEGACY_SITE_ENABLED" "$DISABLED_SITES_DIR/presek.enabled.disabled.$(date +%Y%m%d%H%M%S)"
    fi
    if [ -e "$LEGACY_SITE_AVAILABLE" ] && grep -q "server_name .*presek.live" "$LEGACY_SITE_AVAILABLE"; then
      mv "$LEGACY_SITE_AVAILABLE" "$DISABLED_SITES_DIR/presek.available.disabled.$(date +%Y%m%d%H%M%S)"
    fi

    nginx -t
    systemctl restart nginx
  else
    echo "Skipping nginx install/update (INSTALL_NGINX=$INSTALL_NGINX)." >&2
  fi

  systemctl restart "${APP_SERVICES[@]}"
  systemctl start presek.target

  ENABLE_PUBLIC_CHECK=0 "$SMOKE_SCRIPT"

  echo ""
  echo "Deployment files installed."
  echo "Check services with:"
  echo "  sudo systemctl status presek.target"
  echo "  sudo journalctl -u presek-fastapi.service -f"
  echo "Release root:"
  echo "  $APP_ROOT"
  if [ "$INSTALL_NGINX" = "1" ]; then
    echo "nginx:"
    echo "  updated"
  else
    echo "nginx:"
    echo "  unchanged"
  fi
  echo "  sudo bash deploy/backup_postgres.sh"
}

main "$@"
