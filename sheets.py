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
    "CreatedAt": "נוצר בתאריך",
    "UpdatedAt": "עודכן בתאריך",
}
_LABEL_TO_KEY = {v: k for k, v in HEADER_LABELS.items()}

# Weekly class schedule, editable by the client from /admin - stored in a
# second tab on the same spreadsheet rather than env vars, since it needs to
# be updated weekly without touching Render.
SETTINGS_SHEET_TITLE = "הגדרות"
WEEKDAY_LABELS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
# Position in WEEKDAY_LABELS -> Python's date.weekday() (Monday=0..Sunday=6).
WEEKDAY_PY_INDEX = [6, 0, 1, 2, 3, 4, 5]

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
    try:
        return sh.worksheet(SETTINGS_SHEET_TITLE)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SETTINGS_SHEET_TITLE, rows=10, cols=2)
        ws.update(
            range_name="A1:B8",
            values=[["יום", "שם השיעור"]] + [[label, ""] for label in WEEKDAY_LABELS],
        )
        return ws


def get_weekly_schedule():
    """Return {python_weekday_index: class_name} from the settings tab."""
    ws = _get_settings_worksheet()
    rows = ws.get_all_values()[1:]  # skip header row
    schedule = {}
    for i, py_weekday in enumerate(WEEKDAY_PY_INDEX):
        schedule[py_weekday] = rows[i][1] if i < len(rows) and len(rows[i]) > 1 else ""
    return schedule


def update_weekly_schedule(names_by_label):
    """names_by_label: dict of Hebrew day label (WEEKDAY_LABELS) -> class name."""
    ws = _get_settings_worksheet()
    values = [["יום", "שם השיעור"]] + [
        [label, names_by_label.get(label, "")] for label in WEEKDAY_LABELS
    ]
    ws.update(range_name="A1:B8", values=values)


def get_all_registrants():
    """All registrant rows (English-keyed dicts), for the admin dashboard."""
    ws = _get_worksheet()
    return [
        {_LABEL_TO_KEY.get(k, k): v for k, v in row.items()}
        for row in ws.get_all_records()
    ]


def find_registrant(phone):
    """Return the registrant row (dict, with a `_row` sheet row number) or None."""
    ws = _get_worksheet()
    records = ws.get_all_records()
    for i, raw_row in enumerate(records, start=2):  # row 1 is the header
        # Sheet headers are Hebrew (HEADER_LABELS); translate back to the
        # internal English keys the rest of the code uses.
        row = {_LABEL_TO_KEY.get(k, k): v for k, v in raw_row.items()}
        if str(row.get("Phone", "")).strip() == str(phone).strip():
            row["_row"] = i
            return row
    return None


def upsert_registrant(phone, **fields):
    """Create or update a registrant, merging fields so a webhook update
    can't blank out data collected earlier in the registration flow."""
    ws = _get_worksheet()
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
