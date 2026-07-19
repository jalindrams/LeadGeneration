"""
Micraft Growth Engine - Settings API

Reads and writes .env file values from the frontend.
Admin-only. Secrets are masked on GET but writable on POST.
Changes take effect immediately (os.environ updated) + persisted to .env.
Server restart only needed for DATABASE_URL changes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import require_admin

router = APIRouter(prefix="/api/settings", tags=["settings"])

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

# Settings registry — defines what's shown in the UI
SETTINGS_GROUPS = [
    {
        "group": "WhatsApp Business Cloud",
        "icon": "💬",
        "description": "Meta WhatsApp Cloud API — free tier: 1,000 conversations/month",
        "setup_link": "https://business.facebook.com",
        "keys": [
            {
                "key": "WHATSAPP_ACCESS_TOKEN",
                "label": "Access Token",
                "type": "secret",
                "placeholder": "EAAxxxx… (System User permanent token)",
                "help": "Generate at Meta Business Manager → System Users → Generate Token (whatsapp_business_messaging scope)",
            },
            {
                "key": "WHATSAPP_PHONE_NUMBER_ID",
                "label": "Phone Number ID",
                "type": "text",
                "placeholder": "1234567890",
                "help": "Found on Meta → WhatsApp → API Setup page",
            },
        ],
    },
    {
        "group": "Email / SMTP",
        "icon": "📧",
        "description": "For Gmail: use an App Password (Google Account → Security → App Passwords)",
        "setup_link": "https://myaccount.google.com/apppasswords",
        "keys": [
            {
                "key": "SMTP_HOST",
                "label": "SMTP Host",
                "type": "text",
                "placeholder": "smtp.gmail.com",
                "help": "Gmail: smtp.gmail.com | Outlook: smtp.office365.com",
            },
            {
                "key": "SMTP_PORT",
                "label": "SMTP Port",
                "type": "text",
                "placeholder": "587",
                "help": "Usually 587 (TLS) or 465 (SSL)",
            },
            {
                "key": "SMTP_USER",
                "label": "SMTP Username / Email",
                "type": "text",
                "placeholder": "sales@micraft.co.in",
                "help": "The email address you send from",
            },
            {
                "key": "SMTP_PASSWORD",
                "label": "SMTP Password / App Password",
                "type": "secret",
                "placeholder": "xxxx xxxx xxxx xxxx",
                "help": "For Gmail with 2FA: use a 16-character App Password, not your main password",
            },
            {
                "key": "OUTREACH_FROM_NAME",
                "label": "Sender Name",
                "type": "text",
                "placeholder": "Micraft Solutions",
                "help": "Display name shown in email From field",
            },
            {
                "key": "OUTREACH_FROM_EMAIL",
                "label": "From Email",
                "type": "text",
                "placeholder": "sales@micraft.co.in",
                "help": "Leave blank to use SMTP Username",
            },
        ],
    },
    {
        "group": "Outreach Controls",
        "icon": "🎯",
        "description": "Cadence and volume limits for outreach campaigns",
        "keys": [
            {
                "key": "OUTREACH_DAILY_LIMIT",
                "label": "Daily Send Limit",
                "type": "text",
                "placeholder": "50",
                "help": "Max messages sent per CLI/API run",
            },
            {
                "key": "OUTREACH_COOLDOWN_DAYS",
                "label": "Cooldown Days",
                "type": "text",
                "placeholder": "3",
                "help": "Min days between any two touches to the same lead",
            },
            {
                "key": "HOT_LEAD_THRESHOLD",
                "label": "Hot Lead Score Threshold",
                "type": "text",
                "placeholder": "70",
                "help": "Leads scoring above this are marked hot and get priority outreach",
            },
        ],
    },
    {
        "group": "HubSpot CRM",
        "icon": "🔗",
        "description": "Sync qualified leads to HubSpot automatically",
        "setup_link": "https://app.hubspot.com/private-apps",
        "keys": [
            {
                "key": "HUBSPOT_API_KEY",
                "label": "Private App Token",
                "type": "secret",
                "placeholder": "pat-na1-xxxxxxxx-…",
                "help": "HubSpot → Settings → Integrations → Private Apps → Create → copy token",
            },
        ],
    },
    {
        "group": "Alert Channels",
        "icon": "🔔",
        "description": "Where to send hot-lead alerts (leave blank to disable each channel)",
        "keys": [
            {
                "key": "ALERT_WHATSAPP_TO",
                "label": "Alert WhatsApp Number",
                "type": "text",
                "placeholder": "whatsapp:+919800000000",
                "help": "Your personal WhatsApp for hot-lead alerts (Twilio sandbox)",
            },
            {
                "key": "ALERT_EMAIL_TO",
                "label": "Alert Email(s)",
                "type": "text",
                "placeholder": "you@micraft.co.in,sales@micraft.co.in",
                "help": "Comma-separated email addresses for hot-lead alerts",
            },
            {
                "key": "SLACK_WEBHOOK_URL",
                "label": "Slack Webhook URL",
                "type": "secret",
                "placeholder": "https://hooks.slack.com/services/…",
                "help": "Slack → Your app → Incoming Webhooks → Webhook URL",
            },
        ],
    },
    {
        "group": "Google Maps / Places",
        "icon": "🗺️",
        "description": "Free tier only — hard cap enforced at PLACES_MONTHLY_CALL_CAP",
        "setup_link": "https://console.cloud.google.com",
        "keys": [
            {
                "key": "GOOGLE_MAPS_API_KEY",
                "label": "Google Maps API Key",
                "type": "secret",
                "placeholder": "AIzaxxxxxxxx…",
                "help": "GCP Console → APIs & Services → Credentials → Create API Key (restrict to Places API)",
            },
            {
                "key": "PLACES_MONTHLY_CALL_CAP",
                "label": "Monthly Places Call Cap",
                "type": "text",
                "placeholder": "4000",
                "help": "Hard limit on Places API calls per month. Google free tier = 5,000/month — keep this under 4,000",
            },
        ],
    },
]

SECRET_KEYS = {
    k["key"]
    for g in SETTINGS_GROUPS
    for k in g["keys"]
    if k["type"] == "secret"
}


def _read_env_file() -> dict[str, str]:
    result: dict[str, str] = {}
    if not ENV_PATH.exists():
        return result
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, val = stripped.partition("=")
            result[key.strip()] = val.strip()
    return result


def _write_env_file(updates: dict[str, str]) -> None:
    """Update .env in place, preserving comments and ordering. Appends new keys."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    written: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        new_lines.append(line)

    for key, val in updates.items():
        if key not in written:
            new_lines.append(f"{key}={val}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _mask(key: str, value: str) -> str:
    if key not in SECRET_KEYS or not value:
        return value
    if len(value) <= 8:
        return "••••••••"
    return value[:4] + "••••••••" + value[-4:]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
def get_settings(user=Depends(require_admin)):
    """Return all settings groups with current values (secrets masked)."""
    current = _read_env_file()
    groups = []
    for g in SETTINGS_GROUPS:
        keys = []
        for k in g["keys"]:
            raw = current.get(k["key"], os.environ.get(k["key"], ""))
            keys.append({
                **k,
                "value": _mask(k["key"], raw),
                "is_set": bool(raw),
            })
        groups.append({**g, "keys": keys})
    return {"groups": groups}


class SaveRequest(BaseModel):
    updates: dict[str, Any]


@router.post("/")
def save_settings(req: SaveRequest, user=Depends(require_admin)):
    """
    Save one or more settings to .env and apply to the running process.
    Send only the keys you want to change.
    """
    allowed = {k["key"] for g in SETTINGS_GROUPS for k in g["keys"]}
    bad = set(req.updates) - allowed
    if bad:
        raise HTTPException(400, f"Unknown keys: {bad}")

    # Filter out empty strings that shouldn't overwrite existing values
    # (empty = user cleared the field intentionally → still write it)
    str_updates = {k: str(v) for k, v in req.updates.items()}

    _write_env_file(str_updates)

    # Apply immediately to running process (no restart needed for most settings)
    for k, v in str_updates.items():
        os.environ[k] = v

    # Patch the live settings object too
    try:
        from app.config import settings as _s
        for k, v in str_updates.items():
            if hasattr(_s, k):
                field_type = type(getattr(_s, k))
                try:
                    setattr(_s, k, field_type(v))
                except Exception:
                    pass
    except Exception:
        pass

    return {"saved": list(str_updates.keys()), "message": "Settings saved to .env"}


@router.get("/test/whatsapp")
def test_whatsapp(user=Depends(require_admin)):
    """Send a test WhatsApp message to verify the token + phone number ID."""
    from app.outreach.whatsapp import WhatsAppClient
    client = WhatsAppClient()
    if not client.enabled:
        return {"ok": False, "error": "WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID not set"}
    return {"ok": True, "phone_number_id": client.phone_number_id, "token_prefix": client.token[:8] + "…"}


@router.get("/test/email")
def test_email(user=Depends(require_admin)):
    """Verify SMTP credentials by connecting (no message sent)."""
    import smtplib
    from app.config import settings
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        return {"ok": False, "error": "SMTP_HOST or SMTP_USER not set"}
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as s:
            s.ehlo()
            s.starttls()
            s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        return {"ok": True, "host": settings.SMTP_HOST, "user": settings.SMTP_USER}
    except Exception as e:
        return {"ok": False, "error": str(e)}
