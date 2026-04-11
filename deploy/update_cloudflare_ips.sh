#!/usr/bin/env bash
set -euo pipefail

SNIPPET="/etc/nginx/snippets/cloudflare-realip.conf"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

V4="$(curl -fsS --max-time 15 https://www.cloudflare.com/ips-v4)"
V6="$(curl -fsS --max-time 15 https://www.cloudflare.com/ips-v6)"

if [[ -z "$V4" || -z "$V6" ]]; then
  echo "Refusing to write empty range list" >&2
  exit 1
fi

{
  echo "# Generated $(date -u +%F) from https://www.cloudflare.com/ips-v4,v6"
  echo "# Managed by deploy/update_cloudflare_ips.sh — do not edit by hand"
  echo
  while IFS= read -r cidr; do
    [[ -n "$cidr" ]] && echo "set_real_ip_from $cidr;"
  done <<< "$V4"
  echo
  while IFS= read -r cidr; do
    [[ -n "$cidr" ]] && echo "set_real_ip_from $cidr;"
  done <<< "$V6"
  echo
  echo "real_ip_header CF-Connecting-IP;"
  echo "real_ip_recursive on;"
} > "$TMP"

if [[ -f "$SNIPPET" ]] && cmp -s "$TMP" "$SNIPPET"; then
  echo "Cloudflare ranges unchanged."
  exit 0
fi

install -m 0644 "$TMP" "$SNIPPET"

if ! nginx -t; then
  echo "nginx -t failed after update — manual intervention required" >&2
  exit 1
fi

systemctl reload nginx
echo "Cloudflare ranges updated and nginx reloaded."
