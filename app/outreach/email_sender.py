"""
Micraft Growth Engine - Email Sender

Sends HTML emails via SMTP. Config in .env:
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=sales@micraft.co.in
    SMTP_PASSWORD=your_app_password
    OUTREACH_FROM_NAME=Micraft Solutions
    OUTREACH_FROM_EMAIL=sales@micraft.co.in

For Gmail: use an App Password (not your main password).
Google Account → Security → 2-Step Verification → App Passwords.
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("outreach_email")

_FULL_HTML = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 14px; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
  p {{ line-height: 1.6; }}
  ul {{ line-height: 1.8; }}
  a {{ color: #0070f3; }}
  .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #eee; font-size: 12px; color: #888; }}
</style>
</head>
<body>
{body}
<div class="footer">
  <p>Micraft Solutions Pvt Ltd | Pune, Maharashtra<br>
  <a href="https://micraft.co.in">micraft.co.in</a> |
  <a href="mailto:sales@micraft.co.in">sales@micraft.co.in</a><br>
  <small>To unsubscribe, reply with "unsubscribe" in the subject.</small></p>
</div>
</body>
</html>
"""


class EmailSender:
    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.from_name = getattr(settings, "OUTREACH_FROM_NAME", "Micraft Solutions")
        self.from_email = getattr(settings, "OUTREACH_FROM_EMAIL", settings.SMTP_USER)
        self.enabled = bool(self.host and self.user and self.password)

    def send(self, to_email: str, subject: str, html_body: str) -> dict:
        """
        Send an HTML email.
        Returns {"success": bool, "error": str|None}
        """
        if not self.enabled:
            log.warning("email_disabled", reason="SMTP not configured")
            return {"success": False, "error": "SMTP not configured"}

        if not to_email or "@" not in to_email:
            return {"success": False, "error": f"invalid email: {to_email}"}

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email

        full_html = _FULL_HTML.format(body=html_body)
        msg.attach(MIMEText(full_html, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.host, self.port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.login(self.user, self.password)
                server.sendmail(self.from_email, [to_email], msg.as_string())
            log.info("email_sent", to=to_email.split("@")[1], subject=subject[:50])
            return {"success": True, "error": None}
        except Exception as e:
            log.error("email_send_error", to=to_email[:20], error=str(e)[:200])
            return {"success": False, "error": str(e)[:200]}
