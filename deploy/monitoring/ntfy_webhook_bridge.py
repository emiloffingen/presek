#!/usr/bin/env python3
"""Convert Alertmanager webhook payloads into ntfy.sh notifications."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

ENV_FILE = os.environ.get("PRESEK_ENV", "/home/emiloffingen/presek-runtime/shared/.env")
LISTEN_HOST = os.environ.get("NTFY_BRIDGE_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("NTFY_BRIDGE_PORT", "25826"))


def _load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        with open(ENV_FILE, encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def _clean_topic(topic: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", str(topic or "").strip())
    return cleaned[:64]


def _send_ntfy(topic: str, token: str, title: str, message: str, tags: str, priority: str) -> None:
    clean_topic = _clean_topic(topic)
    if not clean_topic or not message.strip():
        return

    params = urllib.parse.urlencode(
        {
            "title": title[:120],
            "tags": tags[:120],
            "priority": priority,
        }
    )
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    if token and token != "YOUR_NTFY_TOKEN_HERE":
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://ntfy.sh/{urllib.parse.quote(clean_topic, safe='')}?{params}"
    request = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10):
        return


class AlertWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        payload = json.loads(self.rfile.read(length) or b"{}")
        env = _load_env()
        topic = env.get("NTFY_TOPIC", os.environ.get("NTFY_TOPIC", "presek.live-vesti"))
        token = env.get("NTFY_TOKEN", os.environ.get("NTFY_TOKEN", ""))

        for alert in payload.get("alerts", []):
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            alert_name = labels.get("alertname", "Alert")
            severity = labels.get("severity", "warning")
            status = alert.get("status", payload.get("status", "firing"))
            summary = annotations.get("summary", alert_name)
            description = annotations.get("description", "")
            title = f"[{status.upper()}] {summary}"
            body = description or json.dumps(labels, indent=2, sort_keys=True)

            if status == "resolved":
                tags = "white_check_mark"
                priority = "2"
            elif severity == "critical":
                tags = "rotating_light,critical"
                priority = "5"
            else:
                tags = "warning"
                priority = "3"

            try:
                _send_ntfy(topic, token, title, body, tags, priority)
            except Exception as exc:  # noqa: BLE001 - bridge must stay up
                print(f"ntfy delivery failed: {exc}", file=sys.stderr)

        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    server = HTTPServer((LISTEN_HOST, LISTEN_PORT), AlertWebhookHandler)
    print(f"Alertmanager ntfy bridge listening on http://{LISTEN_HOST}:{LISTEN_PORT}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
