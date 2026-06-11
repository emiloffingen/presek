#!/usr/bin/env bash
# Install Alertmanager, ntfy bridge, and Prometheus exporters for Presek.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PRESEK_ENV:-/home/emiloffingen/presek-runtime/shared/.env}"
ALERTMANAGER_VERSION="${ALERTMANAGER_VERSION:-0.27.0}"
POSTGRES_EXPORTER_VERSION="${POSTGRES_EXPORTER_VERSION:-0.15.0}"
REDIS_EXPORTER_VERSION="${REDIS_EXPORTER_VERSION:-1.62.0}"
NGINX_EXPORTER_VERSION="${NGINX_EXPORTER_VERSION:-1.3.0}"
CELERY_EXPORTER_VERSION="${CELERY_EXPORTER_VERSION:-0.10.4}"
INSTALL_DIR="${INSTALL_DIR:-/opt/prometheus}"
BRIDGE_DIR="${BRIDGE_DIR:-/opt/presek-monitoring}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run as root (sudo) to install system services." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

apt-get update
apt-get install -y curl tar

mkdir -p "$INSTALL_DIR" "$BRIDGE_DIR" /etc/alertmanager /etc/default

install -m 0755 "$REPO_ROOT/deploy/monitoring/ntfy_webhook_bridge.py" "$BRIDGE_DIR/ntfy_webhook_bridge.py"
install -m 0644 "$REPO_ROOT/deploy/monitoring/alertmanager.yml" /etc/alertmanager/alertmanager.yml
install -m 0644 "$REPO_ROOT/deploy/monitoring/prometheus.yml" /etc/prometheus/prometheus.yml
install -m 0644 "$REPO_ROOT/deploy/monitoring/prometheus_rules.yml" /etc/prometheus/rules/presek.yml
install -m 0644 "$REPO_ROOT/deploy/nginx/monitoring-stub-status.conf" /etc/nginx/conf.d/presek-monitoring-stub-status.conf

if [[ ! -x "$INSTALL_DIR/alertmanager" ]]; then
  tmp="$(mktemp -d)"
  curl -fsSL "https://github.com/prometheus/alertmanager/releases/download/v${ALERTMANAGER_VERSION}/alertmanager-${ALERTMANAGER_VERSION}.linux-amd64.tar.gz" \
    | tar -xz -C "$tmp"
  install -m 0755 "$tmp/alertmanager-${ALERTMANAGER_VERSION}.linux-amd64/alertmanager" "$INSTALL_DIR/alertmanager"
  install -m 0755 "$tmp/alertmanager-${ALERTMANAGER_VERSION}.linux-amd64/amtool" "$INSTALL_DIR/amtool"
  rm -rf "$tmp"
fi

if [[ ! -x /usr/local/bin/postgres_exporter ]]; then
  tmp="$(mktemp -d)"
  curl -fsSL "https://github.com/prometheus-community/postgres_exporter/releases/download/v${POSTGRES_EXPORTER_VERSION}/postgres_exporter-${POSTGRES_EXPORTER_VERSION}.linux-amd64.tar.gz" \
    | tar -xz -C "$tmp"
  install -m 0755 "$tmp/postgres_exporter-${POSTGRES_EXPORTER_VERSION}.linux-amd64/postgres_exporter" /usr/local/bin/postgres_exporter
  rm -rf "$tmp"
fi

if [[ ! -x /usr/local/bin/redis_exporter ]]; then
  tmp="$(mktemp -d)"
  curl -fsSL "https://github.com/oliver006/redis_exporter/releases/download/v${REDIS_EXPORTER_VERSION}/redis_exporter-v${REDIS_EXPORTER_VERSION}.linux-amd64.tar.gz" \
    | tar -xz -C "$tmp"
  install -m 0755 "$tmp/redis_exporter-v${REDIS_EXPORTER_VERSION}.linux-amd64/redis_exporter" /usr/local/bin/redis_exporter
  rm -rf "$tmp"
fi

if [[ ! -x /usr/local/bin/nginx-prometheus-exporter ]]; then
  tmp="$(mktemp -d)"
  curl -fsSL "https://github.com/nginxinc/nginx-prometheus-exporter/releases/download/v${NGINX_EXPORTER_VERSION}/nginx-prometheus-exporter_${NGINX_EXPORTER_VERSION}_linux_amd64.tar.gz" \
    | tar -xz -C "$tmp"
  install -m 0755 "$tmp/nginx-prometheus-exporter" /usr/local/bin/nginx-prometheus-exporter
  rm -rf "$tmp"
fi

if [[ ! -x /usr/local/bin/celery-exporter ]]; then
  tmp="$(mktemp -d)"
  curl -fsSL "https://github.com/danihodovic/celery-exporter/releases/download/v${CELERY_EXPORTER_VERSION}/celery-exporter" \
    -o "$tmp/celery-exporter"
  install -m 0755 "$tmp/celery-exporter" /usr/local/bin/celery-exporter
  rm -rf "$tmp"
fi

cat >/etc/default/postgres_exporter <<EOF
DATA_SOURCE_NAME=${DATABASE_URL}
EOF
chmod 0600 /etc/default/postgres_exporter

redis_addr="${REDIS_ADDR:-127.0.0.1:6379}"
redis_password=""
if [[ -n "${REDIS_URL:-}" ]]; then
  read -r redis_addr redis_password <<<"$(python3 - <<'PY'
import os
from urllib.parse import urlparse
parsed = urlparse(os.environ["REDIS_URL"])
host = parsed.hostname or "127.0.0.1"
port = parsed.port or 6379
print(f"{host}:{port}", parsed.password or os.environ.get("REDIS_PASSWORD", ""))
PY
)"
elif [[ -n "${REDIS_PASSWORD:-}" ]]; then
  redis_password="${REDIS_PASSWORD}"
fi

cat >/etc/default/redis_exporter <<EOF
REDIS_ADDR=${redis_addr}
REDIS_PASSWORD=${redis_password}
EOF
chmod 0600 /etc/default/redis_exporter

cat >/etc/systemd/system/presek-ntfy-bridge.service <<EOF
[Unit]
Description=Presek Alertmanager to ntfy bridge
After=network-online.target

[Service]
Type=simple
Environment=PRESEK_ENV=${ENV_FILE}
ExecStart=/usr/bin/python3 ${BRIDGE_DIR}/ntfy_webhook_bridge.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/alertmanager.service <<EOF
[Unit]
Description=Alertmanager for Presek
After=network-online.target presek-ntfy-bridge.service

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/alertmanager \\
  --config.file=/etc/alertmanager/alertmanager.yml \\
  --storage.path=${INSTALL_DIR}/alertmanager-data \\
  --web.listen-address=127.0.0.1:9093 \\
  --cluster.listen-address=
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/postgres_exporter.service <<EOF
[Unit]
Description=PostgreSQL Prometheus exporter
After=network-online.target postgresql.service

[Service]
Type=simple
EnvironmentFile=/etc/default/postgres_exporter
ExecStart=/usr/local/bin/postgres_exporter --web.listen-address=127.0.0.1:9187
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/redis_exporter.service <<EOF
[Unit]
Description=Redis Prometheus exporter
After=network-online.target redis-server.service

[Service]
Type=simple
EnvironmentFile=/etc/default/redis_exporter
ExecStart=/bin/bash -c 'exec /usr/local/bin/redis_exporter --web.listen-address=127.0.0.1:9121 --redis.addr="\${REDIS_ADDR}" \${REDIS_PASSWORD:+--redis.password="\$REDIS_PASSWORD"}'
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/nginx_exporter.service <<EOF
[Unit]
Description=Nginx Prometheus exporter
After=network-online.target nginx.service

[Service]
Type=simple
ExecStart=/usr/local/bin/nginx-prometheus-exporter -web.listen-address=127.0.0.1:9113 -nginx.scrape-uri=http://127.0.0.1:8080/stub_status
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/celery_exporter.service <<EOF
[Unit]
Description=Celery Prometheus exporter
After=network-online.target

[Service]
Type=simple
EnvironmentFile=-${ENV_FILE}
ExecStart=/bin/bash -c 'exec /usr/local/bin/celery-exporter --broker-url="\${REDIS_URL:-redis://127.0.0.1:6379/0}" --host=127.0.0.1 --port=9808'
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

/usr/sbin/nginx -t
systemctl reload nginx

systemctl daemon-reload
systemctl enable --now presek-ntfy-bridge.service alertmanager.service \
  postgres_exporter.service redis_exporter.service nginx_exporter.service celery_exporter.service
systemctl restart prometheus.service

echo "Alertmanager UI: http://127.0.0.1:9093"
echo "ntfy bridge: http://127.0.0.1:25826/"
echo "Exporters: postgres=9187 redis=9121 nginx=9113 celery=9808"
