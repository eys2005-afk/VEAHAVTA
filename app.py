import os
from datetime import date

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_cors import CORS

from nedarim import TIERS, build_iframe_transaction, build_payment_url
from sheets import find_registrant, upsert_registrant

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")
CORS(app)

# The class changes daily, so the name shown under the logo can be set per
# day of the week via env vars (falling back to CLASS_NAME, then a
# placeholder). Python's date.weekday(): Monday=0 ... Sunday=6.
CLASS_NAME_ENV_BY_WEEKDAY = {
    6: "CLASS_NAME_SUNDAY",
    0: "CLASS_NAME_MONDAY",
    1: "CLASS_NAME_TUESDAY",
    2: "CLASS_NAME_WEDNESDAY",
    3: "CLASS_NAME_THURSDAY",
    4: "CLASS_NAME_FRIDAY",
    5: "CLASS_NAME_SATURDAY",
}


def get_class_name():
    day_var = CLASS_NAME_ENV_BY_WEEKDAY[date.today().weekday()]
    return (
        os.environ.get(day_var)
        or os.environ.get("CLASS_NAME")
        or "שם השיעור - טרם נמסר"
    )


MARITAL_STATUSES = ["רווק/ה", "בזוגיות", "נשוי/אה"]

# Per Nedarim Plus's official iframe docs: their CallBack always originates
# from this IP - checked (not enforced yet) to guard against spoofing once
# the callback is confirmed working end-to-end.
NEDARIM_CALLBACK_IP = "18.194.219.73"


def _get_request_value(key):
    if request.is_json:
        return (request.get_json(silent=True) or {}).get(key)
    return request.form.get(key)


@app.route("/")
def index():
    return render_template("index.html", tiers=TIERS, class_name=get_class_name())


@app.route("/check-phone", methods=["POST"])
def check_phone():
    phone = _get_request_value("phone")
    tier = _get_request_value("tier")

    if not phone or not tier:
        return jsonify({"error": "phone and tier are required"}), 400

    if tier not in TIERS or not TIERS[tier]["enabled"]:
        return jsonify({"error": "invalid or disabled tier"}), 400

    registrant = find_registrant(phone)
    if registrant:
        # Already registered - skip straight to payment, with a "welcome
        # back" greeting there instead of the new-registrant details form.
        return jsonify(
            {"known": True, "redirect": url_for("pay", phone=phone, tier=tier, returning=1)}
        )

    return jsonify({"known": False, "redirect": url_for("details", phone=phone, tier=tier)})


@app.route("/details", methods=["GET", "POST"])
def details():
    if request.method == "GET":
        phone = request.args.get("phone", "")
        tier = request.args.get("tier", "")
        return render_template(
            "details.html",
            phone=phone,
            tier=tier,
            tiers=TIERS,
            marital_statuses=MARITAL_STATUSES,
        )

    phone = request.form.get("phone")
    tier = request.form.get("tier")
    name = request.form.get("name")
    email = request.form.get("email")
    marital_status = request.form.get("marital_status")

    if not phone or not tier or not name or not email or not marital_status:
        return render_template(
            "details.html",
            phone=phone,
            tier=tier,
            tiers=TIERS,
            marital_statuses=MARITAL_STATUSES,
            error="נא למלא את כל השדות",
        )

    upsert_registrant(
        phone,
        Name=name,
        Email=email,
        MaritalStatus=marital_status,
        Tier=tier,
        Status="pending",
    )
    return redirect(url_for("pay", phone=phone, tier=tier))


@app.route("/pay")
def pay():
    phone = request.args.get("phone")
    tier = request.args.get("tier")
    returning = request.args.get("returning") == "1"

    if not phone or not tier or tier not in TIERS or not TIERS[tier]["enabled"]:
        return redirect(url_for("index"))

    registrant = find_registrant(phone) or {}
    return render_template(
        "pay.html",
        tier_label=TIERS[tier]["label"],
        amount=TIERS[tier]["amount"],
        returning=returning,
        transaction=build_iframe_transaction(
            phone,
            tier,
            name=registrant.get("Name", ""),
            email=registrant.get("Email", ""),
        ),
    )


@app.route("/webhook/nedarim", methods=["GET", "POST"])
def webhook_nedarim():
    # NOTE: field names below (Status, Id, TransactionId, Param1, Param2) are
    # best-guess placeholders based on Nedarim Plus's general documentation
    # and other live integrations. They must be verified against a real
    # callback payload once the client shares Mosad ID / test access - see
    # README for the recommended ₪1 real-card test-and-capture approach.
    #
    # Accepts both GET and POST since it's unconfirmed which one Nedarim
    # Plus actually uses for this redirect-style payment form.
    payload = {
        **request.args.to_dict(),
        **request.form.to_dict(),
        **(request.get_json(silent=True) or {}),
    }
    source_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    app.logger.warning(
        "webhook_nedarim hit: method=%s ip=%s (expected %s) args=%s form=%s",
        request.method,
        source_ip,
        NEDARIM_CALLBACK_IP,
        dict(request.args),
        dict(request.form),
    )

    phone = payload.get("Param1") or payload.get("param1")
    tier = payload.get("Param2") or payload.get("param2")
    status = payload.get("Status")
    transaction_id = payload.get("TransactionId") or payload.get("Id")

    if not phone:
        return jsonify({"error": "missing phone (param1)"}), 400

    # "OK" confirmed from a real working Nedarim Plus integration; "1" kept
    # as a fallback guess in case this account's callback shape differs.
    upsert_registrant(
        phone,
        Tier=tier or "",
        Status="paid" if status in ("OK", "1") else "failed",
        TransactionId=transaction_id or "",
    )

    return jsonify({"ok": True})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True)
