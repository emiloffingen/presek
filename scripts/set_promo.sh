#!/bin/bash
# set_promo.sh - safely change the ad promo discount.
#
# Updates PROMO_DISCOUNT in .env, rebuilds the frontend (which derives
# PUBLIC_PROMO_DISCOUNT from it) and restarts the API + frontend so the display
# and the amount actually charged never drift apart.
#
# Usage:
#   scripts/set_promo.sh 0.15    # 15% off
#   scripts/set_promo.sh 15%     # same
#   scripts/set_promo.sh 0       # end the promo
set -euo pipefail

APP_DIR="/root/presek"
ENV_FILE="$APP_DIR/.env"

raw="${1:-}"
if [ -z "$raw" ]; then
  echo "usage: $0 <discount, e.g. 0.15 or 15%>" >&2
  exit 2
fi

case "$raw" in
  *%) val="$(awk "BEGIN{printf \"%.4f\", ${raw%\%}/100}")" ;;
  *)  val="$raw" ;;
esac

awk "BEGIN{exit !($val >= 0 && $val <= 0.95)}" || {
  echo "discount must be between 0 and 0.95" >&2
  exit 2
}

if grep -qE '^PROMO_DISCOUNT=' "$ENV_FILE"; then
  sed -i "s/^PROMO_DISCOUNT=.*/PROMO_DISCOUNT=$val/" "$ENV_FILE"
else
  printf '\nPROMO_DISCOUNT=%s\n' "$val" >> "$ENV_FILE"
fi
echo "PROMO_DISCOUNT set to $val in $ENV_FILE"

echo "Rebuilding frontend (PUBLIC_PROMO_DISCOUNT=$val)..."
PROMO_DISCOUNT="$val" APP_ROOT="$APP_DIR" WEB_DIR="$APP_DIR/web" FORCE_WEB_BUILD=1 \
  bash "$APP_DIR/deploy/ensure_astro_build.sh"

tmux kill-window -t presek:astro 2>/dev/null || true
tmux kill-window -t presek:fastapi 2>/dev/null || true
echo "Done. astro + fastapi are restarting (watchdog respawns within ~30s)."
