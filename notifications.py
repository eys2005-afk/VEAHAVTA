"""WhatsApp notifications to the client (Noa) via Meta's WhatsApp Cloud API
directly (not Twilio - see git history for that version, abandoned
2026-10 because it needed a paid Twilio account just to register a
Sender), on new registrations and successful payments - best-effort
only: a failure here must never break registration or the payment
webhook, so notify_whatsapp() catches everything itself and just
returns False, rather than raising.

Needs three Render env vars:
- WHATSAPP_PHONE_NUMBER_ID - the sending number's Phone Number ID (not
  the phone number itself), from the Meta app's WhatsApp API Setup page.
- WHATSAPP_ACCESS_TOKEN - a permanent token for a System User with
  whatsapp_business_messaging + whatsapp_business_management access to
  that WhatsApp Business Account (Business Settings -> System Users ->
  Generate New Token, expiration "Never") - NOT the temporary 24h token
  the API Setup page's own "Generate access token" button gives, which
  would silently stop working a day after deploy.
- WHATSAPP_TO - the recipient (Noa), digits only with country code, e.g.
  972501234567 (no +, no whatsapp: prefix - this is Meta's own API, not
  Twilio's).

Sends go through a pre-approved WhatsApp Message Template (name +
language + body parameters), NOT a freeform text message - same
underlying WhatsApp Business Messaging policy reason as the old Twilio
integration: a business-initiated notification like these (the recipient
never messaged first, so there's no open 24h session window) requires an
approved template. Each call site passes the template's name directly
(e.g. "registration_notification", "payment_notification") - see README
for the exact wording submitted for approval in WhatsApp Manager, and
their language is Hebrew ("he").
"""
import logging
import os

import requests

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"


def notify_whatsapp(template_name, variables):
    """Best-effort WhatsApp send via a pre-approved Message Template.
    Returns True on success, False on anything else (missing config,
    Meta API error, network issue) - callers don't need to wrap this in
    their own try/except.

    `template_name` - the approved template's name in WhatsApp Manager.
    `variables` - ordered list of strings filling the template's {{1}},
    {{2}}, ... body placeholders in order."""
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip()
    to_raw = os.environ.get("WHATSAPP_TO", "").strip()

    if not (phone_number_id and access_token and to_raw):
        logger.warning(
            "notify_whatsapp: WHATSAPP_PHONE_NUMBER_ID/WHATSAPP_ACCESS_TOKEN/WHATSAPP_TO "
            "not fully set on Render - skipping notification."
        )
        return False

    payload = {
        "messaging_product": "whatsapp",
        "to": to_raw,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "he"},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(v)} for v in variables],
                }
            ],
        },
    }

    try:
        response = requests.post(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
    except Exception:
        logger.exception("notify_whatsapp: send failed")
        return False

    # Success was previously silent - logged nothing at all, the same as
    # a message that was never attempted - which made it impossible to
    # confirm a send from Render's logs alone (only a missing-config
    # warning or a send-failed exception were ever logged). This is the
    # one line that actually says it worked - .warning(), not .info():
    # nothing in this file (or app.py's own diagnostic logging) has ever
    # used .info(), and Python's default root logger level is WARNING, so
    # an .info() call here would silently never reach Render's logs at
    # all without extra logging config this app doesn't have anywhere.
    # Message ID extraction is wrapped separately so a surprise response
    # shape can only cost us that one detail, never turn an actual
    # successful send into a reported failure (still returns True below).
    message_id = "?"
    try:
        message_id = response.json()["messages"][0]["id"]
    except Exception:
        pass
    logger.warning("notify_whatsapp: sent %s to %s (message id %s)", template_name, to_raw, message_id)

    try:
        # Best-effort too - the message already sent successfully above,
        # so a Sheets hiccup here must not turn a real success into a
        # reported failure. /admin shows this count to the client.
        import sheets

        sheets.increment_whatsapp_sent_count()
    except Exception:
        logger.exception("notify_whatsapp: sent OK but failed to update the sent-count in Sheets")

    return True
