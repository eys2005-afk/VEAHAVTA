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

Sends go through a pre-approved WhatsApp Content Template (content_sid +
content_variables), NOT a freeform body string. Confirmed live on Render
2026-10-10: WhatsApp's Business Messaging policy requires a business-
initiated notification like these (the recipient never messaged first, so
there's no open 24h session window) to use an approved template - a plain
body= send is rejected outright with "ContentSid Required", regardless of
whether this is the Sandbox or a real WhatsApp sender. Each call site
passes the Render env var name holding its template's approved Content
SID (e.g. TWILIO_CONTENT_SID_REGISTRATION, TWILIO_CONTENT_SID_PAYMENT) -
see README for how to create/approve a template and the exact wording
used here.

DEFAULT_WHATSAPP_FROM below is a real WhatsApp sender already set up for
this account (not the generic shared Twilio Sandbox number) - override it
with TWILIO_WHATSAPP_FROM only if that sender ever changes.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_WHATSAPP_FROM = "whatsapp:+972535634674"


def _whatsapp_number(raw):
    raw = raw.strip()
    return raw if raw.startswith("whatsapp:") else f"whatsapp:{raw}"


def notify_whatsapp(content_sid_env, variables):
    """Best-effort WhatsApp send via a pre-approved Content Template.
    Returns True on success, False on anything else (missing config,
    Twilio error, network issue) - callers don't need to wrap this in
    their own try/except.

    `content_sid_env` - name of the Render env var holding the approved
    template's Content SID (set once the template is approved in Twilio's
    Content Template Builder - see README).
    `variables` - ordered list of strings filling the template's {{1}},
    {{2}}, ... placeholders in order."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    to_raw = os.environ.get("TWILIO_WHATSAPP_TO", "").strip()
    from_raw = os.environ.get("TWILIO_WHATSAPP_FROM", DEFAULT_WHATSAPP_FROM).strip()
    content_sid = os.environ.get(content_sid_env, "").strip()

    if not (account_sid and auth_token and to_raw and content_sid):
        logger.warning(
            "notify_whatsapp: TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_WHATSAPP_TO/%s "
            "not fully set on Render - skipping notification.",
            content_sid_env,
        )
        return False

    try:
        from twilio.rest import Client

        client = Client(account_sid, auth_token)
        client.messages.create(
            from_=_whatsapp_number(from_raw),
            to=_whatsapp_number(to_raw),
            content_sid=content_sid,
            content_variables=json.dumps(
                {str(i + 1): v for i, v in enumerate(variables)}, ensure_ascii=False
            ),
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
