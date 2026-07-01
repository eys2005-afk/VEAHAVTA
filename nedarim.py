import os
from urllib.parse import urlencode

# Prices per the client's voice-message brief (single=30, weekly=50).
# Monthly amount is still unconfirmed (see README "Open items").
TIERS = {
    "single": {
        "label": "שיעור בודד",
        "amount": 30,
        "recurring": False,
        "enabled": True,
    },
    "weekly": {
        "label": "מנוי שבועי",
        "amount": 50,
        "recurring": False,
        "enabled": True,
    },
    "monthly": {
        "label": "מנוי חודשי (הוראת קבע)",
        "amount": 150,  # TODO: confirm real monthly price with the client.
        "recurring": True,
        # Disabled until Nedarim Plus's recurring-payment param is confirmed.
        "enabled": False,
    },
}

NEDARIM_BASE_URL = "https://www.matara.pro/nedarimplus/Online/"


def build_payment_url(phone, tier_key):
    tier = TIERS.get(tier_key)
    if not tier or not tier.get("enabled"):
        raise ValueError(f"Unknown or disabled tier: {tier_key}")

    params = {
        "Mosad": os.environ.get("NEDARIM_MOSAD_ID", ""),
        # Nedarim Plus requires a per-institution API key alongside Mosad -
        # confirmed by cross-referencing several other live integrations.
        "ApiValid": os.environ.get("NEDARIM_API_VALID", ""),
        "Amount": tier["amount"],
        "AmountLock": 1,
        "CallBack": os.environ.get("NEDARIM_CALLBACK_URL", ""),
        # Capitalized Param1/Param2 match the field names used by other
        # live Nedarim Plus integrations - still needs confirmation against
        # a real callback payload (see README).
        "Param1": phone,
        "Param2": tier_key,
    }

    if tier["recurring"]:
        # TODO: confirm the real param name/value for monthly recurring
        # (הוראת קבע) payments with Nedarim Plus support.
        params["Tashlumim"] = os.environ.get("NEDARIM_MONTHLY_RECURRING_PARAM", "")

    return f"{NEDARIM_BASE_URL}?{urlencode(params)}"
