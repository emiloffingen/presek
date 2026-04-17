import json, os, logging, httpx

log = logging.getLogger("presek")

class BreakingNewsNotifier:
    def __init__(self, topic, threshold=3):
        self.topic             = topic
        self.threshold         = threshold
        self._notified         = set()  # avoid re-notifying same cluster in same session

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

    def notify_score_change(self, headline, score, cluster_id, teams=None):
        """Instant notification for match score updates."""
        # We don't use _notified set here because we WANT to re-notify on score change
        score_key = f"score:{cluster_id}:{score}"
        if score_key in self._notified:
            return

        title = f"ГОЛ! {score}" if "0" not in score else f"Резултат: {score}"
        msg = f"{headline}\n\nНов резултат: {score}"
        if teams:
            msg = f"{teams}\n{msg}"

        data = {
            "topic":   self.topic,
            "title":   title,
            "message": msg,
            "tags":    ["soccer", "goal_net", "bell"],
            "priority": 5, # Max priority for scores
            "click":   f"https://presek.mk/cluster/{cluster_id}" if cluster_id else "https://presek.mk"
        }
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(f"https://ntfy.sh/{self.topic}", json=data)
                resp.raise_for_status()
            self._notified.add(score_key)
            log.info(f"[notifier] Sent score update for {cluster_id}: {score}")
        except Exception as e:
            log.warning(f"[notifier] Score notification failed: {e}")

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
        self._notified.add(cluster_id)
