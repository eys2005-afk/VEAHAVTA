"""WhatsApp notifications to the client (Noa) via Twilio, on new
registrations and successful payments - best-effort only: a failure here
must never break registration or the payment webhook, so notify_whatsapp()
catches everything itself and just returns False, rather than raising.

Needs three Render env vars:
- TWILIO_ACCOUNT_SID
- TWILIO_AUTH_TOKEN
- TWILIO_WHATSAPP_TO - the recipient, e.g. whatsapp:+972501234567
  (a bare +972... is accepted too; the whatsapp: prefix is added if
  missing)

This is still Twilio's free WhatsApp Sandbox (see README/CLAUDE.md) - a
shared "from" number, fine for this low-volume use case. If the client
ever upgrades to a real dedicated WhatsApp sender, override it with
TWILIO_WHATSAPP_FROM rather than changing this file.
"""
import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_WHATSAPP_FROM = "whatsapp:+972535634674"


def _whatsapp_number(raw):
    raw = raw.strip()
    return raw if raw.startswith("whatsapp:") else f"whatsapp:{raw}"


def notify_whatsapp(message):
    """Best-effort WhatsApp send via Twilio. Returns True on success, False
    on anything else (missing config, Twilio error, network issue) -
    callers don't need to wrap this in their own try/except."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    to_raw = os.environ.get("TWILIO_WHATSAPP_TO", "").strip()
    from_raw = os.environ.get("TWILIO_WHATSAPP_FROM", DEFAULT_WHATSAPP_FROM).strip()

    if not (account_sid and auth_token and to_raw):
        logger.warning(
            "notify_whatsapp: TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_WHATSAPP_TO "
            "not fully set on Render - skipping notification."
        )
        return False

    try:
        from twilio.rest import Client

        client = Client(account_sid, auth_token)
        client.messages.create(
            from_=_whatsapp_number(from_raw),
            to=_whatsapp_number(to_raw),
            body=message,
        )
    except Exception:
        logger.exception("notify_whatsapp: send failed")
        return False

    try:
        # Best-effort too - the message already sent successfully above,
        # so a Sheets hiccup here must not turn a real success into a
        # reported failure. /admin shows this count to track Twilio's
        # one-time free quota (see sheets.get_whatsapp_sent_count).
        import sheets

        sheets.increment_whatsapp_sent_count()
    except Exception:
        logger.exception("notify_whatsapp: sent OK but failed to update the sent-count in Sheets")

    return True
