import os

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_cors import CORS

from nedarim import TIERS, build_payment_url
from sheets import find_registrant, upsert_registrant

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")
CORS(app)


def _get_request_value(key):
    if request.is_json:
        return (request.get_json(silent=True) or {}).get(key)
    return request.form.get(key)


@app.route("/")
def index():
    return render_template("index.html", tiers=TIERS)


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
        # Already registered - skip straight to payment.
        return jsonify({"known": True, "redirect": url_for("pay", phone=phone, tier=tier)})

    return jsonify({"known": False, "redirect": url_for("details", phone=phone, tier=tier)})


@app.route("/details", methods=["GET", "POST"])
def details():
    if request.method == "GET":
        phone = request.args.get("phone", "")
        tier = request.args.get("tier", "")
        return render_template("details.html", phone=phone, tier=tier, tiers=TIERS)

    phone = request.form.get("phone")
    tier = request.form.get("tier")
    name = request.form.get("name")

    if not phone or not tier or not name:
        return render_template(
            "details.html",
            phone=phone,
            tier=tier,
            tiers=TIERS,
            error="נא למלא את כל השדות",
        )

    upsert_registrant(phone, Name=name, Tier=tier, Status="pending")
    return redirect(url_for("pay", phone=phone, tier=tier))


@app.route("/pay")
def pay():
    phone = request.args.get("phone")
    tier = request.args.get("tier")

    if not phone or not tier:
        return redirect(url_for("index"))

    payment_url = build_payment_url(phone, tier)
    return redirect(payment_url)


@app.route("/webhook/nedarim", methods=["POST"])
def webhook_nedarim():
    # NOTE: field names below (Status, Id, TransactionId, param1, param2) are
    # best-guess placeholders based on Nedarim Plus's general documentation.
    # They must be verified against real callback payloads once the client
    # shares Mosad ID / test access.
    payload = request.form.to_dict() or request.get_json(silent=True) or {}

    phone = payload.get("param1")
    tier = payload.get("param2")
    status = payload.get("Status")
    transaction_id = payload.get("TransactionId") or payload.get("Id")

    if not phone:
        return jsonify({"error": "missing phone (param1)"}), 400

    upsert_registrant(
        phone,
        Tier=tier or "",
        Status="paid" if str(status) == "1" else "failed",
        TransactionId=transaction_id or "",
    )

    return jsonify({"ok": True})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True)
