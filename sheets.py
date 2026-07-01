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


def find_registrant(phone):
    """Return the registrant row (dict, with a `_row` sheet row number) or None."""
    ws = _get_worksheet()
    records = ws.get_all_records()
    for i, row in enumerate(records, start=2):  # row 1 is the header
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
