import os
from urllib.parse import urlencode

# Placeholder pricing/labels - exact class name, session details and prices
# are still pending from the client (see README "Open items").
TIERS = {
    "single": {
        "label": "שיעור בודד",
        "amount": 20,
        "recurring": False,
        "enabled": True,
    },
    "weekly": {
        "label": "מנוי שבועי",
        "amount": 80,
        "recurring": False,
        "enabled": True,
    },
    "monthly": {
        "label": "מנוי חודשי (הוראת קבע)",
        "amount": 150,
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
        "Amount": tier["amount"],
        "AmountLock": 1,
        "CallBack": os.environ.get("NEDARIM_CALLBACK_URL", ""),
        "param1": phone,
        "param2": tier_key,
    }

    if tier["recurring"]:
        # TODO: confirm the real param name/value for monthly recurring
        # (הוראת קבע) payments with Nedarim Plus support.
        params["Tashlumim"] = os.environ.get("NEDARIM_MONTHLY_RECURRING_PARAM", "")

    return f"{NEDARIM_BASE_URL}?{urlencode(params)}"
