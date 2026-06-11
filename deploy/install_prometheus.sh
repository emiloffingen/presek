#!/usr/bin/env bash
# Install a minimal Prometheus + node_exporter stack for Presek (Debian/Ubuntu).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROMETHEUS_VERSION="${PROMETHEUS_VERSION:-2.54.1}"
NODE_EXPORTER_VERSION="${NODE_EXPORTER_VERSION:-1.8.2}"
INSTALL_DIR="${INSTALL_DIR:-/opt/prometheus}"
RULES_DIR="${RULES_DIR:-/etc/prometheus/rules}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run as root (sudo) to install system services." >&2
  exit 1
fi

apt-get update
apt-get install -y curl tar

mkdir -p "$INSTALL_DIR" "$RULES_DIR" /etc/prometheus

if [[ ! -x "$INSTALL_DIR/prometheus" ]]; then
  tmp="$(mktemp -d)"
  curl -fsSL "https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz" \
    | tar -xz -C "$tmp"
  install -m 0755 "$tmp/prometheus-${PROMETHEUS_VERSION}.linux-amd64/prometheus" "$INSTALL_DIR/prometheus"
  install -m 0755 "$tmp/prometheus-${PROMETHEUS_VERSION}.linux-amd64/promtool" "$INSTALL_DIR/promtool"
  rm -rf "$tmp"
fi

if [[ ! -x /usr/local/bin/node_exporter ]]; then
  tmp="$(mktemp -d)"
  curl -fsSL "https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz" \
    | tar -xz -C "$tmp"
  install -m 0755 "$tmp/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64/node_exporter" /usr/local/bin/node_exporter
  rm -rf "$tmp"
fi

install -m 0644 "$REPO_ROOT/deploy/monitoring/prometheus.yml" /etc/prometheus/prometheus.yml
install -m 0644 "$REPO_ROOT/deploy/monitoring/prometheus_rules.yml" "$RULES_DIR/presek.yml"

cat >/etc/systemd/system/prometheus.service <<EOF
[Unit]
Description=Prometheus for Presek
After=network-online.target

[Service]
Type=simple
ExecStart=$INSTALL_DIR/prometheus \\
  --config.file=/etc/prometheus/prometheus.yml \\
  --storage.tsdb.path=$INSTALL_DIR/data \\
  --web.listen-address=127.0.0.1:9090
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/node_exporter.service <<EOF
[Unit]
Description=Node Exporter
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/node_exporter --web.listen-address=127.0.0.1:9100
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now node_exporter.service prometheus.service

echo "Prometheus UI: http://127.0.0.1:9090 (SSH tunnel recommended)"
echo "Presek metrics scrape target: localhost:5001/metrics"
