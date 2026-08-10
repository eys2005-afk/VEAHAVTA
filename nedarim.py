import os
from urllib.parse import urlencode

# Prices per the client (single=30/evening, punch card=75/3 entries).
# Monthly amount is still unconfirmed (see README "Open items").
# "entries": N marks a tier as a multi-visit punch card - paying for it sets
# EntriesRemaining=N on the registrant; returning with entries left checks
# them in (decrementing the count) instead of charging again (see app.py).
TIERS = {
    "single": {
        "label": "ערב בודד",
        "amount": 30,
        "recurring": False,
        "enabled": True,
        "entries": None,
    },
    "weekly": {
        "label": "כרטיסייה - 3 כניסות",
        "amount": 75,
        "recurring": False,
        "enabled": True,
        "entries": 3,
    },
    "monthly": {
        "label": "מנוי חודשי (הוראת קבע)",
        "amount": 150,  # TODO: confirm real monthly price with the client.
        "recurring": True,
        # Disabled until Nedarim Plus's recurring-payment param is confirmed.
        "enabled": False,
        "entries": None,
    },
}

# Lowercase path + lowercase "mosad" param - verified against the real
# Mosad ID (7016996): the capitalized "Online/?Mosad=" form throws a server
# error on Nedarim Plus's side, while this lowercase form works correctly
# with Amount/AmountLock/CallBack/Param1/Param2, and needs no ApiValid.
NEDARIM_BASE_URL = "https://www.matara.pro/nedarimplus/online/"


def test_charge_amount():
    """TEMPORARY: while confirming the real Mosad ID / NEDARIM_API_VALID
    integration end-to-end, set NEDARIM_TEST_AMOUNT=1 on Render to force
    every real charge down to ₪1 regardless of tier - so live-testing the
    payment flow doesn't cost real tier prices. The site still *displays*
    each tier's real price (₪30, ₪75, ...); only the amount actually sent
    to Nedarim Plus is overridden. Unset the env var on Render once testing
    is done to go back to real prices."""
    raw = os.environ.get("NEDARIM_TEST_AMOUNT", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def build_payment_params(phone, tier_key, tier=None):
    """Shared param set for both the full-page redirect and the iframe
    postMessage handshake - verified against the real Mosad ID (7016996)
    for the redirect form; the iframe form uses the same field names but
    hasn't been tested live yet (see README).

    `tier` lets callers pass a resolved tier dict directly (e.g. app.py's
    dynamic free-mode/workshop tiers, which aren't in the static TIERS
    dict below); defaults to looking `tier_key` up in TIERS."""
    tier = tier or TIERS.get(tier_key)
    if not tier or not tier.get("enabled"):
        raise ValueError(f"Unknown or disabled tier: {tier_key}")

    params = {
        "mosad": os.environ.get("NEDARIM_MOSAD_ID", ""),
        "Amount": test_charge_amount() or tier["amount"],
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


def build_payment_url(phone, tier_key, tier=None):
    """Full-page redirect form - verified working against the real Mosad ID."""
    params = build_payment_params(phone, tier_key, tier=tier)
    return f"{NEDARIM_BASE_URL}?{urlencode(params)}"


def build_iframe_transaction(phone, tier_key, name="", email="", tier=None):
    """Config for the iframe's 'FinishTransaction2' postMessage, per Nedarim
    Plus's official iframe integration guide (PDF supplied by the client) -
    not a guess. Requires NEDARIM_API_VALID, a separate auth token that
    must be requested from Nedarim Plus support (see README); the CallBack
    mechanism itself is only documented for this iframe flow, not the plain
    redirect form.

    `tier` - see build_payment_params."""
    tier = tier or TIERS.get(tier_key)
    if not tier or not tier.get("enabled"):
        raise ValueError(f"Unknown or disabled tier: {tier_key}")

    # Split on the *last* space so a multi-word first name (e.g. "בן דוד
    # כהן") still gets a real surname, not just the last of three words
    # attached to nothing. app.py's /details already requires at least two
    # words before it ever reaches here, but this stays defensive in case
    # a registrant's name was saved some other way (e.g. directly in the
    # Sheet by the client).
    name_parts = (name or "").split()
    if len(name_parts) >= 2:
        first_name, last_name = " ".join(name_parts[:-1]), name_parts[-1]
    else:
        first_name, last_name = (name_parts[0] if name_parts else ""), ""

    return {
        "Mosad": os.environ.get("NEDARIM_MOSAD_ID", ""),
        "ApiValid": os.environ.get("NEDARIM_API_VALID", ""),
        "PaymentType": "HK" if tier["recurring"] else "Ragil",
        "Amount": test_charge_amount() or tier["amount"],
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
