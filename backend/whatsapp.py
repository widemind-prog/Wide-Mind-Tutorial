"""
Wide Mind Study Director — WhatsApp provider abstraction.

Phase 1 (default): ManualProvider
  Does not call any API. Messages land in study_director_messages with
  status='queued'. Admin copies and sends from WhatsApp Business App (free).

Phase 2: MetaCloudProvider
  Set WHATSAPP_PROVIDER=meta_cloud in Render env vars, plus:
    WHATSAPP_TOKEN            — Meta Cloud API bearer token
    WHATSAPP_PHONE_NUMBER_ID  — your registered phone number ID
  No code changes needed to switch providers.
"""

import os


class WhatsAppProvider:
    def send(self, to: str, message: str) -> dict:
        raise NotImplementedError


class ManualProvider(WhatsAppProvider):
    """Phase 1 — stores in DB, admin sends manually via WhatsApp Business App."""
    def send(self, to: str, message: str) -> dict:
        return {"status": "queued", "provider": "manual", "provider_message_id": None}


class MetaCloudProvider(WhatsAppProvider):
    """Phase 2 — Meta WhatsApp Business Cloud API."""
    def __init__(self):
        self.token    = os.environ.get("WHATSAPP_TOKEN", "")
        self.phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
        self.api_url  = f"https://graph.facebook.com/v19.0/{self.phone_id}/messages"

    def send(self, to: str, message: str) -> dict:
        import requests as req
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to.lstrip("+"),
            "type": "text",
            "text": {"body": message, "preview_url": False},
        }
        try:
            resp = req.post(self.api_url, json=payload, headers=headers, timeout=10)
            data = resp.json()
            if resp.status_code == 200:
                msg_id = (data.get("messages") or [{}])[0].get("id")
                return {"status": "sent", "provider": "meta_cloud",
                        "provider_message_id": msg_id}
            return {"status": "failed", "provider": "meta_cloud",
                    "provider_message_id": None, "failure_reason": str(data)}
        except Exception as e:
            return {"status": "failed", "provider": "meta_cloud",
                    "provider_message_id": None, "failure_reason": str(e)}


def get_provider() -> WhatsAppProvider:
    if os.environ.get("WHATSAPP_PROVIDER", "manual").lower() == "meta_cloud":
        return MetaCloudProvider()
    return ManualProvider()
