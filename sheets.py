import json
import os
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = [
    "Phone",
    "Name",
    "Email",
    "MaritalStatus",
    "Tier",
    "Status",
    "Amount",
    "TransactionId",
    "EntriesRemaining",
    "CreatedAt",
    "UpdatedAt",
]

# Internal (English) key -> the actual column header text in the Sheet.
# Keeps the code's field names stable while showing readable Hebrew column
# titles to the client in the spreadsheet itself.
HEADER_LABELS = {
    "Phone": "טלפון",
    "Name": "שם",
    "Email": "אימייל",
    "MaritalStatus": "מצב משפחתי",
    "Tier": "מסלול",
    "Status": "סטטוס",
    "Amount": "סכום",
    "TransactionId": "מזהה עסקה",
    "EntriesRemaining": "כניסות נותרו",
    "CreatedAt": "נוצר בתאריך",
    "UpdatedAt": "עודכן בתאריך",
}
_LABEL_TO_KEY = {v: k for k, v in HEADER_LABELS.items()}

# Weekly class schedule + site toggles, all editable by the client from
# /admin - stored in a second tab on the same spreadsheet rather than env
# vars/code, since they need to change often without touching Render/GitHub.
SETTINGS_SHEET_TITLE = "הגדרות"
WEEKDAY_LABELS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
# Position in WEEKDAY_LABELS -> Python's date.weekday() (Monday=0..Sunday=6).
WEEKDAY_PY_INDEX = [6, 0, 1, 2, 3, 4, 5]

# Extra settings rows, below the 7 weekday rows in the same tab.
FREE_MODE_LABEL = "מצב חינם (כן/לא)"
WORKSHOP_NAME_LABEL = "סדנה - שם"
WORKSHOP_AMOUNT_LABEL = "סדנה - מחיר"
WORKSHOP_ENABLED_LABEL = "סדנה - פעילה (כן/לא)"
EXTRA_SETTINGS_LABELS = [
    FREE_MODE_LABEL,
    WORKSHOP_NAME_LABEL,
    WORKSHOP_AMOUNT_LABEL,
    WORKSHOP_ENABLED_LABEL,
]
SETTINGS_ROW_LABELS = WEEKDAY_LABELS + EXTRA_SETTINGS_LABELS

_client = None


def get_sheets_client():
    """Lazily build and cache an authorized gspread client."""
    global _client
    if _client is not None:
        return _client

    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT")
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "service-account.json")
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)

    _client = gspread.authorize(creds)
    return _client


def _get_worksheet():
    client = get_sheets_client()
    sheet_id = os.environ["GOOGLE_SHEET_ID"]
    return client.open_by_key(sheet_id).sheet1


def _get_settings_worksheet():
    client = get_sheets_client()
    sheet_id = os.environ["GOOGLE_SHEET_ID"]
    sh = client.open_by_key(sheet_id)
    end_row = 1 + len(SETTINGS_ROW_LABELS)
    try:
        return sh.worksheet(SETTINGS_SHEET_TITLE)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SETTINGS_SHEET_TITLE, rows=end_row + 2, cols=2)
        ws.update(
            range_name=f"A1:B{end_row}",
            values=[["הגדרה", "ערך"]] + [[label, ""] for label in SETTINGS_ROW_LABELS],
        )
        return ws


def _read_settings_rows():
    """Return {row_label: value} for every row in SETTINGS_ROW_LABELS."""
    ws = _get_settings_worksheet()
    rows = ws.get_all_values()[1:]  # skip header row
    values = {}
    for i, label in enumerate(SETTINGS_ROW_LABELS):
        values[label] = rows[i][1] if i < len(rows) and len(rows[i]) > 1 else ""
    return values


def get_weekly_schedule():
    """Return {python_weekday_index: class_name} from the settings tab."""
    values = _read_settings_rows()
    return {WEEKDAY_PY_INDEX[i]: values[label] for i, label in enumerate(WEEKDAY_LABELS)}


def get_site_settings():
    """Free-mode toggle + a single temporary workshop tier, both editable
    from /admin without a code change or redeploy."""
    values = _read_settings_rows()
    try:
        workshop_amount = int(values.get(WORKSHOP_AMOUNT_LABEL, ""))
    except (TypeError, ValueError):
        workshop_amount = None

    return {
        "free_mode": values.get(FREE_MODE_LABEL, "").strip() == "כן",
        "workshop_name": values.get(WORKSHOP_NAME_LABEL, ""),
        "workshop_amount": workshop_amount,
        "workshop_enabled": values.get(WORKSHOP_ENABLED_LABEL, "").strip() == "כן",
    }


def update_settings(names_by_label, free_mode, workshop_name, workshop_amount, workshop_enabled):
    """names_by_label: dict of Hebrew day label (WEEKDAY_LABELS) -> class name."""
    ws = _get_settings_worksheet()
    row_values = {label: names_by_label.get(label, "") for label in WEEKDAY_LABELS}
    row_values[FREE_MODE_LABEL] = "כן" if free_mode else "לא"
    row_values[WORKSHOP_NAME_LABEL] = workshop_name
    row_values[WORKSHOP_AMOUNT_LABEL] = str(workshop_amount) if workshop_amount not in (None, "") else ""
    row_values[WORKSHOP_ENABLED_LABEL] = "כן" if workshop_enabled else "לא"

    end_row = 1 + len(SETTINGS_ROW_LABELS)
    values = [["הגדרה", "ערך"]] + [[label, row_values[label]] for label in SETTINGS_ROW_LABELS]
    ws.update(range_name=f"A1:B{end_row}", values=values)


def get_all_registrants():
    """All registrant rows (English-keyed dicts), for the admin dashboard."""
    ws = _get_worksheet()
    return [
        {_LABEL_TO_KEY.get(k, k): v for k, v in row.items()}
        for row in ws.get_all_records(numericise_ignore=["all"])
    ]


def _normalize_phone(phone):
    """Digits only - so '058-740-1791' and '0587401791' are treated as the
    *same* registrant instead of two unrelated ones. A real case: one
    registrant ended up with two rows, one from each format, and only the
    one matching whatever format a given request happened to use ever got
    updated (e.g. a payment webhook updating a row the visitor's original
    registration never touched). Applied only for comparisons/storage -
    never changes what a route receives from the visitor."""
    return "".join(ch for ch in str(phone) if ch.isdigit())


def find_registrant(phone):
    """Return the registrant row (dict, with a `_row` sheet row number) or
    None. If a phone somehow has more than one row (e.g. repeat test
    submissions that each ended up appending instead of updating), the
    *last* (most recent) match wins - not the first/oldest one - so a
    stale early row never shadows real, current data.

    numericise_ignore=["all"]: gspread's get_all_records() auto-converts
    number-looking cell values to real Python int/float by default,
    *regardless* of the cell's actual stored format - "0542236262" (a
    phone number, stored as text) was silently becoming the int 542236262,
    dropping the leading zero. The str(...) comparison below then never
    matched a real phone (submitted with its leading zero) against
    anything in the Sheet, no matter how many times a registrant re-
    submitted - this, not name-splitting, was the actual reason every
    /pay lookup came back empty and Nedarim Plus kept rejecting the
    transaction for a "missing" name that was never actually missing."""
    ws = _get_worksheet()
    records = ws.get_all_records(numericise_ignore=["all"])
    target = _normalize_phone(phone)
    match = None
    for i, raw_row in enumerate(records, start=2):  # row 1 is the header
        # Sheet headers are Hebrew (HEADER_LABELS); translate back to the
        # internal English keys the rest of the code uses.
        row = {_LABEL_TO_KEY.get(k, k): v for k, v in raw_row.items()}
        if _normalize_phone(row.get("Phone", "")) == target and target:
            row["_row"] = i
            match = row
    return match


def upsert_registrant(phone, **fields):
    """Create or update a registrant, merging fields so a webhook update
    can't blank out data collected earlier in the registration flow.
    Stores the phone digits-only (see _normalize_phone) so future lookups
    stay consistent regardless of how it was originally typed/formatted."""
    ws = _get_worksheet()
    phone = _normalize_phone(phone)
    existing = find_registrant(phone)
    now = datetime.now(timezone.utc).isoformat()

    if existing:
        row_number = existing.pop("_row")
        merged = {**existing, **fields}
        merged["Phone"] = phone
        merged["UpdatedAt"] = now
        values = [merged.get(h, "") for h in HEADERS]
        end_cell = rowcol_to_a1(row_number, len(HEADERS))
        ws.update(range_name=f"A{row_number}:{end_cell}", values=[values])
        return merged

    merged = {h: "" for h in HEADERS}
    merged.update(fields)
    merged["Phone"] = phone
    merged["CreatedAt"] = now
    merged["UpdatedAt"] = now
    values = [merged.get(h, "") for h in HEADERS]
    ws.append_row(values)
    return merged
