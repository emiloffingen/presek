import logging
import os
from typing import Optional
from tasks.utils import send_email

log = logging.getLogger("presek")

class Notifier:
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
                to_address=recipient
            )

