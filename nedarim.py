import os
from urllib.parse import urlencode

# Prices per the client (single=30/evening, punch card=75/3 entries,
# monthly=150/month confirmed 2026-08-11).
# "entries": N marks a tier as a multi-visit punch card - paying for it sets
# EntriesRemaining=N on the registrant; returning with entries left checks
# them in (decrementing the count) instead of charging again (see app.py).
# "months": N on a recurring tier sets Nedarim's Tashlumim (number of
# months to charge) - the registrant picks a commitment length (1-12) up
# front rather than an open-ended standing order; see build_payment_params.
MONTHLY_AMOUNT = 150

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
}

def months_label(n):
    """Hebrew month count with correct grammar - '1 חודש' (not '1
    חודשים'), '2 חודשים' (not the dual 'חודשיים', to keep every option
    reading as a plain number + unit), '3 חודשים' etc."""
    return "חודש" if n == 1 else f"{n} חודשים"


# One tier per commitment length (1-12 months) - generated rather than
# hand-written so the full range is consistent (same amount/label pattern)
# and adding e.g. an 18-month option later is a one-line range() change.
for _months in range(1, 13):
    TIERS[f"monthly_{_months}"] = {
        "label": f"מנוי חודשי - {months_label(_months)} (הוראת קבע)",
        "amount": MONTHLY_AMOUNT,
        "recurring": True,
        "enabled": True,
        "entries": None,
        "months": _months,
    }
del _months

# Lowercase path + lowercase "mosad" param - verified against the real
# Mosad ID (7016996): the capitalized "Online/?Mosad=" form throws a server
# error on Nedarim Plus's side, while this lowercase form works correctly
# with Amount/AmountLock/CallBack/Param1/Param2, and needs no ApiValid.
NEDARIM_BASE_URL = "https://www.matara.pro/nedarimplus/online/"

# Iframe "Method 3" - per Nedarim Plus's own integration instructions
# (client, 2026-10-19): the only iframe version that offers Bit/Google
# Pay/Apple Pay/"העברה בקליק" as payment-method choices, not just cards.
# Must be loaded with www (no apex-domain confirmation for /v3/ specifically
# - see pay.html's origin check, which still accepts both).
NEDARIM_IFRAME_V3_URL = "https://www.matara.pro/nedarimplus/iframe/v3/"


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
        # Per the official PostNedarim parameter table: for PaymentType=HK,
        # Tashlumim is "מספר חודשים לחיוב (ללא הגבלה יש להשאיר ריק)" - number
        # of months to charge, leave empty for unlimited. Each monthly tier
        # now picks a fixed commitment length (see TIERS' "months") rather
        # than an open-ended standing order.
        params["Tashlumim"] = str(tier["months"]) if tier.get("months") else ""

    return params


def build_payment_url(phone, tier_key, tier=None):
    """Full-page redirect form - verified working against the real Mosad ID."""
    params = build_payment_params(phone, tier_key, tier=tier)
    return f"{NEDARIM_BASE_URL}?{urlencode(params)}"


def build_iframe_transaction(phone, tier_key, name="", email="", tier=None):
    """Config for the iframe's 'StartPayment' postMessage (iframe "Method
    3" - NEDARIM_IFRAME_V3_URL), matching Nedarim Plus's own integration
    instructions for it (client, 2026-10-19) - this is the version that
    offers Bit/Google Pay/Apple Pay as payment-method choices inside the
    iframe, not just cards (the older FinishTransaction2/v2 iframe never
    did). Field *names* carried over unchanged from the confirmed v2
    integration (same PostNedarim parameter table applies to both), with
    two deliberate changes for Bit specifically (see below): no Param1,
    and the whole name still goes in FirstName with LastName left '' (that
    was confirmed against v2's own sample page, sample2.html - v3's
    sample3.html hasn't been checked, but there's no reason to expect
    Nedarim split name handling between their own iframe versions).

    `tier` - see build_payment_params.

    IMPORTANT - no Param1: sending Param1 at all hides the Bit option from
    the payment-method list, per Nedarim's own instructions - Param2 is
    used for callers' identifier instead. Since this app already needs
    *two* values back in the webhook (phone, tier), both now travel packed
    together in the one available slot, as "<phone>:<tier_key>" - see
    webhook_nedarim in app.py, which splits them back apart (and still
    accepts the old Param1=phone/Param2=tier shape too, from the previous
    iframe version, in case of an in-flight transaction right at deploy
    time)."""
    tier = tier or TIERS.get(tier_key)
    if not tier or not tier.get("enabled"):
        raise ValueError(f"Unknown or disabled tier: {tier_key}")

    return {
        "Mosad": os.environ.get("NEDARIM_MOSAD_ID", ""),
        "ApiValid": os.environ.get("NEDARIM_API_VALID", ""),
        "Zeout": "",
        "PaymentType": "HK" if tier["recurring"] else "Ragil",
        "Amount": test_charge_amount() or tier["amount"],
        # See build_payment_params: Tashlumim is the fixed number of months
        # to charge for a recurring tier (empty would mean unlimited). Note
        # for Bit specifically: Nedarim only offers it for a single ("Ragil")
        # payment, never a standing order - recurring (monthly_*) tiers
        # simply won't show Bit as an option inside the iframe; nothing to
        # enforce on this app's side.
        "Tashlumim": (str(tier["months"]) if tier.get("months") else "") if tier["recurring"] else "1",
        "Currency": "1",
        "FirstName": name or "",
        "LastName": "",
        "Street": "",
        "City": "",
        "Phone": phone,
        "Mail": email,
        "Groupe": "",
        "Comment": "",
        "Param2": f"{phone}:{tier_key}",
        "CallBack": os.environ.get("NEDARIM_CALLBACK_URL", ""),
        "CallBackMailError": os.environ.get("NEDARIM_CALLBACK_MAIL_ERROR", ""),
    }
