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

# Lowercase path + lowercase "mosad" param - verified against the real
# Mosad ID (7016996): the capitalized "Online/?Mosad=" form throws a server
# error on Nedarim Plus's side, while this lowercase form works correctly
# with Amount/AmountLock/CallBack/Param1/Param2, and needs no ApiValid.
NEDARIM_BASE_URL = "https://www.matara.pro/nedarimplus/online/"


def build_payment_url(phone, tier_key):
    tier = TIERS.get(tier_key)
    if not tier or not tier.get("enabled"):
        raise ValueError(f"Unknown or disabled tier: {tier_key}")

    params = {
        "mosad": os.environ.get("NEDARIM_MOSAD_ID", ""),
        "Amount": tier["amount"],
        "AmountLock": 1,
        "CallBack": os.environ.get("NEDARIM_CALLBACK_URL", ""),
        "Param1": phone,
        "Param2": tier_key,
    }

    if tier["recurring"]:
        # TODO: confirm the real param name/value for monthly recurring
        # (הוראת קבע) payments with Nedarim Plus support.
        params["Tashlumim"] = os.environ.get("NEDARIM_MONTHLY_RECURRING_PARAM", "")

    return f"{NEDARIM_BASE_URL}?{urlencode(params)}"
