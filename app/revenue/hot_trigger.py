"""
Micraft Growth Engine - Hot Lead Trigger (Module 3)
Fires instant alerts when a lead's score crosses HOT_LEAD_THRESHOLD (default 70).

Channels (each activates only when its credentials are set in .env):
  - WhatsApp via Twilio  (TWILIO_ACCOUNT_SID / AUTH_TOKEN / WHATSAPP_FROM / ALERT_WHATSAPP_TO)
  - Slack incoming webhook (SLACK_WEBHOOK_URL)
  - Email via SMTP       (SMTP_HOST / SMTP_USER / SMTP_PASSWORD / ALERT_EMAIL_TO)

With no channel configured, alerts are logged only — safe to call always.
"""

import smtplib
from email.mime.text import MIMEText

import httpx

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("hot_trigger")


def _format_alert(lead) -> str:
    return (
        "🔥 HOT LEAD\n\n"
        f"Company:  {lead.company_name}\n"
        f"Contact:  {lead.full_name or 'Unknown'} — {lead.title or 'title unknown'}\n"
        f"Location: {lead.location or '-'}\n"
        f"Phone:    {lead.phone or '-'}\n"
        f"Email:    {lead.email or '-'}\n"
        f"Score:    {lead.score}/100\n"
        f"Source:   {lead.source}\n\n"
        "⚡ Call within 15 minutes."
    )


def _send_whatsapp(body: str) -> bool:
    if not (settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN
            and settings.TWILIO_WHATSAPP_FROM and settings.ALERT_WHATSAPP_TO):
        return False
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    sent = False
    for to in settings.ALERT_WHATSAPP_TO.split(","):
        to = to.strip()
        if not to:
            continue
        try:
            resp = httpx.post(
                url,
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                data={"From": settings.TWILIO_WHATSAPP_FROM, "To": to, "Body": body},
                timeout=15,
            )
            if resp.status_code in (200, 201):
                sent = True
                log.info("whatsapp_alert_sent", to=to)
            else:
                log.error("whatsapp_alert_failed", to=to, status=resp.status_code,
                          body=resp.text[:200])
        except httpx.HTTPError as e:
            log.error("whatsapp_alert_error", to=to, error=str(e))
    return sent


def _send_slack(body: str) -> bool:
    if not settings.SLACK_WEBHOOK_URL:
        return False
    try:
        resp = httpx.post(settings.SLACK_WEBHOOK_URL, json={"text": body}, timeout=15)
        ok = resp.status_code == 200
        log.info("slack_alert_sent") if ok else log.error("slack_alert_failed",
                                                          status=resp.status_code)
        return ok
    except httpx.HTTPError as e:
        log.error("slack_alert_error", error=str(e))
        return False


def _send_email(body: str, subject: str) -> bool:
    if not (settings.SMTP_HOST and settings.ALERT_EMAIL_TO):
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_USER or "alerts@micraft.local"
        recipients = [a.strip() for a in settings.ALERT_EMAIL_TO.split(",") if a.strip()]
        msg["To"] = ", ".join(recipients)
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
            s.starttls()
            if settings.SMTP_USER:
                s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.sendmail(msg["From"], recipients, msg.as_string())
        log.info("email_alert_sent", to=recipients)
        return True
    except Exception as e:
        log.error("email_alert_error", error=str(e))
        return False


def trigger_if_hot(lead) -> bool:
    """
    Fire alerts if the lead is hot. Returns True if any alert was delivered.
    Safe to call for every stored/rescored lead.
    """
    if (lead.score or 0) < settings.HOT_LEAD_THRESHOLD:
        return False

    body = _format_alert(lead)
    delivered = False
    delivered |= _send_whatsapp(body)
    delivered |= _send_slack(body)
    delivered |= _send_email(body, f"🔥 HOT LEAD: {lead.company_name} ({lead.score}/100)")

    if not delivered:
        log.warning("hot_lead_no_channel_configured", company=lead.company_name,
                    score=lead.score)
    return delivered
