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


def build_payment_params(phone, tier_key):
    """Shared param set for both the full-page redirect and the iframe
    postMessage handshake - verified against the real Mosad ID (7016996)
    for the redirect form; the iframe form uses the same field names but
    hasn't been tested live yet (see README)."""
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

    return params


def build_payment_url(phone, tier_key):
    """Full-page redirect form - verified working against the real Mosad ID."""
    params = build_payment_params(phone, tier_key)
    return f"{NEDARIM_BASE_URL}?{urlencode(params)}"


def build_iframe_transaction(phone, tier_key, name="", email=""):
    """Config for the iframe's 'FinishTransaction2' postMessage, per Nedarim
    Plus's official iframe integration guide (PDF supplied by the client) -
    not a guess. Requires NEDARIM_API_VALID, a separate auth token that
    must be requested from Nedarim Plus support (see README); the CallBack
    mechanism itself is only documented for this iframe flow, not the plain
    redirect form."""
    tier = TIERS.get(tier_key)
    if not tier or not tier.get("enabled"):
        raise ValueError(f"Unknown or disabled tier: {tier_key}")

    first_name, _, last_name = (name or "").partition(" ")

    return {
        "Mosad": os.environ.get("NEDARIM_MOSAD_ID", ""),
        "ApiValid": os.environ.get("NEDARIM_API_VALID", ""),
        "PaymentType": "HK" if tier["recurring"] else "Ragil",
        "Amount": tier["amount"],
        "Tashlumim": (
            os.environ.get("NEDARIM_MONTHLY_RECURRING_PARAM", "")
            if tier["recurring"]
            else "1"
        ),
        "Currency": "1",
        "FirstName": first_name,
        "LastName": last_name,
        "Phone": phone,
        "Mail": email,
        "Param1": phone,
        "Param2": tier_key,
        "CallBack": os.environ.get("NEDARIM_CALLBACK_URL", ""),
        "CallBackMailError": os.environ.get("NEDARIM_CALLBACK_MAIL_ERROR", ""),
    }
