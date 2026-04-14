import json, os, logging, httpx

log = logging.getLogger("presek")

class BreakingNewsNotifier:
    def __init__(self, topic, threshold=3):
        self.topic     = topic
        self.threshold = threshold
        self._notified = set()  # avoid re-notifying same cluster in same session

    def send_ntfy(self, title, message, cluster_id=None):
        try:
            data = {
                "topic":   self.topic,
                "title":   title,
                "message": message,
                "tags":    ["newspaper", "rotating_light"],
                "priority": 4,
                "click":   f"https://presek.mk/cluster/{cluster_id}" if cluster_id else "https://presek.mk"
            }
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(f"https://ntfy.sh/{self.topic}", json=data)
                resp.raise_for_status()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            log.warning(f"[notifier] ntfy error: {e}")

    def send_telegram(self, message, cluster_id=None, image_url=None):
        token = os.environ.get("TELEGRAM_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")

        if not token or not chat_id:
            return

        link = f"https://presek.mk/cluster/{cluster_id}" if cluster_id else "https://presek.mk"

        # Send directly via Telegram Bot API.
        try:
            html_text = f"🚨 <b>ПРЕСЕК — Важна вест</b>\n\n{message}\n\n🔗 <a href='{link}'>Целосна синтеза тука</a>"

            if image_url:
                url = f"https://api.telegram.org/bot{token}/sendPhoto"
                payload = {
                    "chat_id": chat_id,
                    "photo": image_url,
                    "caption": html_text,
                    "parse_mode": "HTML",
                }
            else:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": html_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                }

            with httpx.Client(timeout=8.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            log.warning(f"[notifier] telegram bot error: {e}")

    def notify(self, headline, sources_count, cluster_id, description=None, sources=None, image_url=None):
        if cluster_id in self._notified:
            return

        parts = [f"<b>{headline}</b>"]
        if description:
            parts.append(description)
        source_line = f"{sources_count} извори известуваат"
        if sources:
            source_line += f" ({', '.join(sources[:5])})"
        parts.append(f"<i>{source_line}</i>")
        msg = "\n\n".join(parts)

        self.send_ntfy("Важна вест — Пресек", f"{headline}\n({sources_count} извори известуваат)", cluster_id)
        self.send_telegram(msg, cluster_id, image_url=image_url)
        self._notified.add(cluster_id)
