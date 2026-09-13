import logging
import os
from typing import Optional

import httpx

from tasks.utils import send_email
from utils.cache import redis_client

log = logging.getLogger("presek")


class SystemNotifier:
    @staticmethod
    def send_alert(alert_type: str, message: str, context: Optional[dict] = None):
        """Send a notification through configured channels."""
        # Log the error initially as a baseline alert
        full_msg = f"[ALERT][{alert_type}] {message} | Context: {context or {}}"
        log.error(full_msg)

        # Email integration
        smtp_user = os.environ.get("SMTP_USER")
        smtp_pass = os.environ.get("SMTP_PASS")
        recipient = "emiloffingen@gmail.com"

        if smtp_user and smtp_pass:
            send_email(
                html=f"<html><body><h1>Alert: {alert_type}</h1><p>{message}</p><pre>{context}</pre></body></html>",
                subject=f"Presek Alert: {alert_type}",
                smtp_user=smtp_user,
                smtp_pass=smtp_pass,
                to_address=recipient,
            )


class BreakingNewsNotifier:
    def __init__(self, topic, threshold=3):
        self.topic = topic
        self.threshold = threshold

    def _is_notified(self, key: str) -> bool:
        """Check Redis to see if we already notified this event."""
        try:
            return bool(redis_client.get(f"notifier:sent:{key}"))
        except Exception as e:
            log.debug(f"[notifier] Redis error in _is_notified: {e}")
            return False

    def _mark_as_notified(self, key: str, expiry: int = 86400):
        """Mark event as notified in Redis with 24h expiry."""
        try:
            redis_client.set(f"notifier:sent:{key}", "1", ex=expiry)
        except Exception as e:
            log.debug(f"[notifier] Redis error in _mark_as_notified: {e}")

    def send_ntfy(self, title, message, cluster_id=None):
        try:
            data = {
                "topic": self.topic,
                "title": title,
                "message": message,
                "tags": ["newspaper", "rotating_light"],
                "priority": 4,
                "click": (f"https://presek.live/cluster/{cluster_id}" if cluster_id else "https://presek.live"),
            }
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(f"https://ntfy.sh/{self.topic}", json=data)
                resp.raise_for_status()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            log.warning(f"[notifier] ntfy error: {e}")

    def notify_score_change(self, headline, score, cluster_id, teams=None):
        """Instant notification for match score updates."""
        score_key = f"score:{cluster_id}:{score}"
        if self._is_notified(score_key):
            return

        title = f"GOL! {score}" if "0" not in score else f"Rezultat: {score}"
        msg = f"{headline}\n\nNov rezultat: {score}"
        if teams:
            msg = f"{teams}\n{msg}"

        data = {
            "topic": self.topic,
            "title": title,
            "message": msg,
            "tags": ["soccer", "goal_net", "bell"],
            "priority": 5,  # Max priority for scores
            "click": (f"https://presek.live/cluster/{cluster_id}" if cluster_id else "https://presek.live"),
        }
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(f"https://ntfy.sh/{self.topic}", json=data)
                resp.raise_for_status()
            self._mark_as_notified(score_key)
            log.info(f"[notifier] Sent score update for {cluster_id}: {score}")
        except Exception as e:
            log.warning(f"[notifier] Score notification failed: {e}")

    def notify(
        self,
        headline,
        sources_count,
        cluster_id,
        description=None,
        sources=None,
        image_url=None,
    ):
        if self._is_notified(cluster_id):
            return

        parts = [f"<b>{headline}</b>"]
        if description:
            parts.append(description)
        source_line = f"{sources_count} izvori izvestuvaat"
        if sources:
            source_line += f" ({', '.join(sources[:5])})"
        parts.append(f"<i>{source_line}</i>")

        self.send_ntfy(
            "Vazna vest — Presek",
            f"{headline}\n({sources_count} izvori izvestuvaat)",
            cluster_id,
        )
        self._mark_as_notified(cluster_id)
