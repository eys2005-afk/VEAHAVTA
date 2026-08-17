import os
import secrets
from datetime import date
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_cors import CORS

from nedarim import TIERS, build_iframe_transaction, build_payment_url, test_charge_amount
from sheets import (
    WEEKDAY_LABELS,
    WEEKDAY_PY_INDEX,
    find_registrant,
    get_all_registrants,
    get_site_settings,
    get_weekly_schedule,
    update_settings,
    upsert_registrant,
)

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
    weekday = date.today().weekday()
    try:
        # The client edits this weekly from /admin - preferred over the env
        # vars below, which just stay as a fallback if the sheet is
        # unreachable (so a transient Sheets error can't break the landing
        # page for visitors).
        name = get_weekly_schedule().get(weekday)
        if name:
            return name
    except Exception:
        pass

    day_var = CLASS_NAME_ENV_BY_WEEKDAY[weekday]
    return (
        os.environ.get(day_var)
        or os.environ.get("CLASS_NAME")
        or "שם השיעור - טרם נמסר"
    )


def get_active_tiers():
    """The tiers shown on the site right now: the static TIERS, plus
    /admin's temporary workshop tier toggle - editable by the client
    without a redeploy. Falls back to the plain static tiers if the sheet
    is unreachable, so a transient Sheets error can't break checkout.

    Free-mode (see get_site_settings) is deliberately *not* applied here -
    it no longer changes what's displayed. It only changes what happens at
    checkout (see /pay), so a promo like an opening month stays free in
    practice while visitors still see the real price."""
    tiers = {key: dict(value) for key, value in TIERS.items()}

    try:
        settings = get_site_settings()
    except Exception:
        return tiers

    if settings["workshop_enabled"] and settings["workshop_name"] and settings["workshop_amount"] is not None:
        tiers["workshop"] = {
            "label": settings["workshop_name"],
            "amount": settings["workshop_amount"],
            "recurring": False,
            "enabled": True,
            "entries": None,
        }

    return tiers


MARITAL_STATUSES = ["רווק/ה", "בזוגיות", "נשוי/אה"]

# Per Nedarim Plus's official iframe docs: their CallBack always originates
# from this IP - checked (not enforced yet) to guard against spoofing once
# the callback is confirmed working end-to-end.
NEDARIM_CALLBACK_IP = "18.194.219.73"

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def _get_request_value(key):
    if request.is_json:
        return (request.get_json(silent=True) or {}).get(key)
    return request.form.get(key)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped


@app.route("/")
def index():
    try:
        free_mode_active = bool(get_site_settings().get("free_mode"))
    except Exception:
        free_mode_active = False
    return render_template(
        "index.html",
        tiers=get_active_tiers(),
        class_name=get_class_name(),
        free_mode=free_mode_active,
    )


@app.route("/check-phone", methods=["POST"])
def check_phone():
    phone = _get_request_value("phone")
    tier = _get_request_value("tier")
    tiers = get_active_tiers()

    if not phone or not tier:
        return jsonify({"error": "phone and tier are required"}), 400

    if tier not in tiers or not tiers[tier]["enabled"]:
        return jsonify({"error": "invalid or disabled tier"}), 400

    registrant = find_registrant(phone)
    if registrant and registrant.get("Name"):
        # Already registered *with a name on file* - skip straight to
        # payment, with a "welcome back" greeting there instead of the
        # new-registrant details form. A row that exists but has no name
        # (e.g. a free-mode registration that only ever collected a phone
        # number) still needs to go through /details - otherwise nobody
        # knows who actually signed up.
        return jsonify(
            {"known": True, "redirect": url_for("pay", phone=phone, tier=tier, returning=1)}
        )

    return jsonify({"known": False, "redirect": url_for("details", phone=phone, tier=tier)})


@app.route("/details", methods=["GET", "POST"])
def details():
    tiers = get_active_tiers()

    if request.method == "GET":
        phone = request.args.get("phone", "")
        tier = request.args.get("tier", "")
        return render_template(
            "details.html",
            phone=phone,
            tier=tier,
            tiers=tiers,
            marital_statuses=MARITAL_STATUSES,
            name="",
            email="",
            marital_status="",
        )

    phone = request.form.get("phone")
    tier = request.form.get("tier")
    name = request.form.get("name")
    email = request.form.get("email")
    marital_status = request.form.get("marital_status")

    # A plain data-quality check (real registrant records) - NOT a Nedarim
    # Plus requirement. Their own reference implementation (sample2.html)
    # sends the whole name as FirstName and always leaves LastName empty,
    # so splitting a single-word name was never actually the cause of the
    # "נא לציין שם פרטי ומשפחה" rejection some registrations ran into (see
    # build_iframe_transaction) - just a coincidentally-matching error text.
    has_full_name = name and len(name.split()) >= 2

    if not phone or not tier or not name or not email or not marital_status or not has_full_name:
        error = "נא למלא את כל השדות"
        if name and not has_full_name:
            error = "נא להזין שם פרטי ושם משפחה (לא רק שם אחד)"

        # Re-render with whatever they already typed still filled in - only
        # the missing field(s) should need re-entering, not the whole form.
        return render_template(
            "details.html",
            phone=phone,
            tier=tier,
            tiers=tiers,
            marital_statuses=MARITAL_STATUSES,
            name=name or "",
            email=email or "",
            marital_status=marital_status or "",
            error=error,
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
    tiers = get_active_tiers()

    if not phone or not tier or tier not in tiers or not tiers[tier]["enabled"]:
        return redirect(url_for("index"))

    tier_config = tiers[tier]
    registrant = find_registrant(phone) or {}

    # Punch-card check-in: if they're still on the same tier they last paid
    # for and have visits left, just check them in - no new charge.
    if tier_config.get("entries") and registrant.get("Tier") == tier:
        try:
            entries_remaining = int(registrant.get("EntriesRemaining") or 0)
        except ValueError:
            entries_remaining = 0
        if entries_remaining > 0:
            upsert_registrant(phone, EntriesRemaining=str(entries_remaining - 1))
            return render_template(
                "checkin.html",
                tier_label=tier_config["label"],
                entries_remaining=entries_remaining - 1,
                free=False,
            )

    # Free-mode (e.g. an opening-month promo, toggled from /admin): the
    # *displayed* price stays real (see get_active_tiers) so visitors still
    # know what it normally costs, but checkout itself is skipped - no
    # charge, register them directly. A tier priced at literally ₪0 (e.g. a
    # free workshop) skips the same way regardless of free-mode.
    try:
        free_mode_active = bool(get_site_settings().get("free_mode"))
    except Exception:
        free_mode_active = False

    if tier_config["amount"] == 0 or free_mode_active:
        upsert_registrant(phone, Tier=tier, Status="free", Amount=0)
        return render_template(
            "checkin.html",
            tier_label=tier_config["label"],
            free=True,
            opening_promo=free_mode_active and tier_config["amount"] > 0,
            real_amount=tier_config["amount"],
        )

    return render_template(
        "pay.html",
        tier_label=tier_config["label"],
        amount=tier_config["amount"],
        test_charge_amount=test_charge_amount(),
        returning=returning,
        transaction=build_iframe_transaction(
            phone,
            tier,
            name=registrant.get("Name", ""),
            email=registrant.get("Email", ""),
            tier=tier_config,
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
    #
    # force=True on get_json: confirmed via a real callback (2026-08-10) that
    # Nedarim Plus doesn't send a Content-Type Flask recognizes as JSON, so
    # request.form/request.args came back empty and get_json(silent=True)
    # (without force) silently found nothing too - the callback was real
    # (from their documented IP) but got dropped with a 400. force=True
    # parses the body as JSON regardless of Content-Type.
    raw_body = request.get_data(as_text=True)
    payload = {
        **request.args.to_dict(),
        **request.form.to_dict(),
        **(request.get_json(silent=True, force=True) or {}),
    }
    source_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    app.logger.warning(
        "webhook_nedarim hit: method=%s ip=%s (expected %s) content_type=%s args=%s form=%s raw_body=%s",
        request.method,
        source_ip,
        NEDARIM_CALLBACK_IP,
        request.content_type,
        dict(request.args),
        dict(request.form),
        raw_body,
    )

    phone = payload.get("Param1") or payload.get("param1")
    tier = payload.get("Param2") or payload.get("param2")
    status = payload.get("Status")
    transaction_id = payload.get("TransactionId") or payload.get("Id")

    if not phone:
        # Still log what we *did* get, even on failure - the whole point of
        # this diagnostic is to catch the field names on the next real
        # callback if this still isn't enough to parse it.
        app.logger.warning("webhook_nedarim: no phone found in payload=%s", payload)
        return jsonify({"error": "missing phone (param1)"}), 400

    # "OK" confirmed from a real working Nedarim Plus integration; "1" kept
    # as a fallback guess in case this account's callback shape differs.
    is_paid = status in ("OK", "1")
    fields = {
        "Tier": tier or "",
        "Status": "paid" if is_paid else "failed",
        "TransactionId": transaction_id or "",
    }

    if is_paid:
        entries = get_active_tiers().get(tier or "", {}).get("entries")
        if entries:
            fields["EntriesRemaining"] = str(entries)

    upsert_registrant(phone, **fields)

    return jsonify({"ok": True})


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if ADMIN_PASSWORD and secrets.compare_digest(password, ADMIN_PASSWORD):
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        error = "סיסמה שגויה"
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin_dashboard():
    if request.method == "POST":
        names_by_label = {
            label: request.form.get(f"day_{i}", "").strip()
            for i, label in enumerate(WEEKDAY_LABELS)
        }
        workshop_amount = request.form.get("workshop_amount", "").strip()
        update_settings(
            names_by_label,
            free_mode=request.form.get("free_mode") == "on",
            workshop_name=request.form.get("workshop_name", "").strip(),
            workshop_amount=workshop_amount or None,
            workshop_enabled=request.form.get("workshop_enabled") == "on",
        )
        return redirect(url_for("admin_dashboard"))

    schedule = get_weekly_schedule()
    day_values = [schedule.get(WEEKDAY_PY_INDEX[i], "") for i in range(len(WEEKDAY_LABELS))]
    settings = get_site_settings()

    return render_template(
        "admin.html",
        weekday_labels=WEEKDAY_LABELS,
        day_values=day_values,
        settings=settings,
        registrants=get_all_registrants(),
        sheet_url=f"https://docs.google.com/spreadsheets/d/{os.environ.get('GOOGLE_SHEET_ID', '')}/edit",
    )


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True)
