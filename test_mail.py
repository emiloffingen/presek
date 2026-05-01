import os
from tasks.utils import send_email

smtp_user = os.environ.get("SMTP_USER")
smtp_pass = os.environ.get("SMTP_PASS")
recipient = "emiloffingen@gmail.com"

if smtp_user and smtp_pass:
    success = send_email(
        html="<html><body><h1>Test Alert</h1><p>If you see this, email alerts are working.</p></body></html>",
        subject="Presek Test Alert",
        smtp_user=smtp_user,
        smtp_pass=smtp_pass,
        to_address=recipient
    )
    print(f"Email sent: {success}")
else:
    print("SMTP credentials missing. Check your .env file.")
