import json, urllib.request, os, logging

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
            req = urllib.request.Request(
                "https://ntfy.sh/",
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            log.warning(f"[notifier] ntfy error: {e}")

    def send_telegram(self, message, cluster_id=None):
        token = os.environ.get("TELEGRAM_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        gw_url = os.environ.get("OPENCLAW_GATEWAY_URL")
        gw_token = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
        
        if not token or not chat_id:
            return
        
        link = f"https://presek.mk/cluster/{cluster_id}" if cluster_id else "https://presek.mk"
        
        # 1. Try OpenClaw Gateway First
        if gw_url and gw_token:
            try:
                # Use HTML for OpenClaw as it's the preferred format in this project
                html_text = f"🚨 <b>ПРЕСЕК — Важна вест</b>\n\n{message}\n\n🔗 <a href='{link}'>Целосна синтеза тука</a>"
                endpoint = f"{gw_url.rstrip('/')}/channels/presekmk/message"
                
                data = json.dumps({
                    "text": html_text,
                    "parse_mode": "HTML"
                }).encode("utf-8")
                
                req = urllib.request.Request(
                    endpoint, 
                    data=data, 
                    headers={
                        "Authorization": f"Bearer {gw_token}",
                        "Content-Type": "application/json"
                    }
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status == 200:
                        return
            except Exception as e:
                log.warning(f"[notifier] openclaw error: {e}, falling back to Bot API")

        # 2. Fallback: Direct Telegram Bot API
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            text = f"🚨 *ПРЕСЕК — Важна вест*\n\n{message}\n\n🔗 [Целосна синтеза тука]({link})"
            
            data = json.dumps({
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False
            }).encode("utf-8")
            
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=8)
        except Exception as e:
            log.warning(f"[notifier] telegram bot error: {e}")

    def notify(self, headline, sources_count, cluster_id):
        if cluster_id in self._notified:
            return
        
        msg = f"{headline}\n({sources_count} извори известуваат)"
        self.send_ntfy("Важна вест — Пресек", msg, cluster_id)
        self.send_telegram(msg, cluster_id)
        self._notified.add(cluster_id)
