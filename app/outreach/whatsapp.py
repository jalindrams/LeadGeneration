"""
Micraft Growth Engine - WhatsApp Business Cloud API Client

Uses Meta's WhatsApp Cloud API (free tier: 1,000 business-initiated
conversations/month). Requires a verified Meta Business account with
a WhatsApp Business number.

Setup (one-time):
  1. business.facebook.com → Add WhatsApp number
  2. Get permanent token: System User → Generate Token (whatsapp_business_messaging)
  3. Submit each template at: WhatsApp Manager → Message Templates
  4. Add to .env:
       WHATSAPP_ACCESS_TOKEN=EAAxxxx...
       WHATSAPP_PHONE_NUMBER_ID=1234567890   (from API setup page)

Template approval takes 0-48h. Once approved, status shows "APPROVED".
"""

from __future__ import annotations

import re
import requests

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("outreach_whatsapp")

META_API_URL = "https://graph.facebook.com/v19.0/{phone_number_id}/messages"


def _normalize_phone(raw: str) -> str | None:
    """Convert any Indian phone to E.164 (91XXXXXXXXXX)."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("91") and len(digits) == 12:
        return digits
    if len(digits) == 10 and digits[0] in "6789":
        return f"91{digits}"
    if digits.startswith("0") and len(digits) == 11:
        return f"91{digits[1:]}"
    return None


class WhatsAppClient:
    """Thin wrapper around Meta WhatsApp Cloud API."""

    def __init__(self):
        self.token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", "")
        self.phone_number_id = getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "")
        self.enabled = bool(self.token and self.phone_number_id)

    def _url(self) -> str:
        return META_API_URL.format(phone_number_id=self.phone_number_id)

    def send_template(
        self,
        to_phone: str,
        template_name: str,
        params: list[str],
        language: str = "en",
    ) -> dict:
        """
        Send a pre-approved template message.

        Returns {"success": bool, "message_id": str|None, "error": str|None}
        """
        if not self.enabled:
            log.warning("whatsapp_disabled", reason="no token or phone_number_id")
            return {"success": False, "message_id": None, "error": "WhatsApp not configured"}

        to = _normalize_phone(to_phone)
        if not to:
            return {"success": False, "message_id": None,
                    "error": f"invalid phone: {to_phone}"}

        body_components = []
        if params:
            body_components.append({
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in params],
            })

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": body_components,
            },
        }

        try:
            r = requests.post(
                self._url(),
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                timeout=20,
            )
            data = r.json()
            if r.status_code == 200 and "messages" in data:
                msg_id = data["messages"][0].get("id")
                log.info("wa_sent", to=to[-4:], template=template_name, msg_id=msg_id)
                return {"success": True, "message_id": msg_id, "error": None}
            else:
                err = data.get("error", {}).get("message", str(data))
                log.warning("wa_api_error", to=to[-4:], template=template_name, error=err)
                return {"success": False, "message_id": None, "error": err}
        except Exception as e:
            log.error("wa_send_exception", error=str(e)[:200])
            return {"success": False, "message_id": None, "error": str(e)[:200]}

    def send_text(self, to_phone: str, text: str) -> dict:
        """
        Send a free-form text message.
        Only works within 24h of a user-initiated conversation.
        """
        if not self.enabled:
            return {"success": False, "message_id": None, "error": "WhatsApp not configured"}

        to = _normalize_phone(to_phone)
        if not to:
            return {"success": False, "message_id": None,
                    "error": f"invalid phone: {to_phone}"}

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        try:
            r = requests.post(
                self._url(),
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                timeout=20,
            )
            data = r.json()
            if r.status_code == 200:
                msg_id = data.get("messages", [{}])[0].get("id")
                return {"success": True, "message_id": msg_id, "error": None}
            err = data.get("error", {}).get("message", str(data))
            return {"success": False, "message_id": None, "error": err}
        except Exception as e:
            return {"success": False, "message_id": None, "error": str(e)[:200]}
