#!/usr/bin/env bash
# Install Grafana with Presek Prometheus datasource and dashboard provisioning.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GRAFANA_VERSION="${GRAFANA_VERSION:-11.5.2}"
INSTALL_DIR="${INSTALL_DIR:-/opt/grafana}"
DASHBOARD_DIR="${DASHBOARD_DIR:-/etc/grafana/dashboards}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run as root (sudo) to install system services." >&2
  exit 1
fi

apt-get update
apt-get install -y curl tar adduser

if [[ ! -x "$INSTALL_DIR/bin/grafana-server" ]]; then
  tmp="$(mktemp -d)"
  curl -fsSL "https://dl.grafana.com/oss/release/grafana-${GRAFANA_VERSION}.linux-amd64.tar.gz" \
    | tar -xz -C "$tmp"
  rm -rf "$INSTALL_DIR"
  mv "$tmp/grafana-v${GRAFANA_VERSION}" "$INSTALL_DIR"
  rm -rf "$tmp"
fi

id -u grafana >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin grafana
mkdir -p "$INSTALL_DIR/data" "$DASHBOARD_DIR" /etc/grafana/provisioning/datasources /etc/grafana/provisioning/dashboards
chown -R grafana:grafana "$INSTALL_DIR" /etc/grafana "$DASHBOARD_DIR"

install -m 0644 "$REPO_ROOT/deploy/monitoring/grafana-datasource.yml" /etc/grafana/provisioning/datasources/prometheus.yml
install -m 0644 "$REPO_ROOT/deploy/monitoring/grafana-dashboards.yml" /etc/grafana/provisioning/dashboards/presek.yml
python3 - <<PY
import json
from pathlib import Path

src = Path("$REPO_ROOT/deploy/monitoring/grafana_dashboard.json")
out = Path("$DASHBOARD_DIR/presek-overview.json")
dashboard = json.loads(src.read_text(encoding="utf-8"))
for key in ("__inputs", "__requires"):
    dashboard.pop(key, None)

def walk(node):
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key == "uid" and value == "\${DS_PROMETHEUS}":
                node[key] = "prometheus"
            else:
                walk(value)
    elif isinstance(node, list):
        for item in node:
            walk(item)

walk(dashboard)
if not dashboard.get("title"):
    dashboard["title"] = "Presek - News Aggregation Monitoring"
if not dashboard.get("uid"):
    dashboard["uid"] = "presek-monitoring"
out.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
PY
chown grafana:grafana "$DASHBOARD_DIR/presek-overview.json"

cat >/etc/default/grafana-server <<EOF
GF_PATHS_CONFIG=/etc/grafana/grafana.ini
GF_PATHS_DATA=${INSTALL_DIR}/data
GF_PATHS_HOME=${INSTALL_DIR}
GF_PATHS_LOGS=/var/log/grafana
GF_PATHS_PLUGINS=${INSTALL_DIR}/data/plugins
GF_PATHS_PROVISIONING=/etc/grafana/provisioning
GF_SERVER_HTTP_ADDR=127.0.0.1
GF_SERVER_HTTP_PORT=3001
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-presek-ops}
GF_USERS_ALLOW_SIGN_UP=false
GF_AUTH_ANONYMOUS_ENABLED=false
EOF
chmod 0600 /etc/default/grafana-server

mkdir -p /var/log/grafana
chown grafana:grafana /var/log/grafana

cat >/etc/systemd/system/grafana-server.service <<EOF
[Unit]
Description=Grafana for Presek
After=network-online.target prometheus.service

[Service]
Type=simple
User=grafana
Group=grafana
EnvironmentFile=/etc/default/grafana-server
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/bin/grafana server --homepath=${INSTALL_DIR}
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now grafana-server.service

echo "Grafana UI: http://127.0.0.1:3001 (admin / see /etc/default/grafana-server)"
echo "Pre-provisioned dashboard folder: Presek / Presek Overview"
