# ואהבת (VEAHAVTA)

QR-code landing page for a class called "ואהבת". Flow:

1. Visitor scans a QR code and lands on `/`.
2. They pick a tier and enter their phone number.
3. Returning registrants skip straight to payment; new registrants fill in
   a short details form (`/details`).
4. They're redirected to Nedarim Plus's hosted payment page (`/pay`) - no
   card data ever touches this server.
5. Nedarim Plus calls back `/webhook/nedarim` on completion, and the
   registrant's row in Google Sheets is updated with payment status.

This mirrors the architecture of the client's other project (`chesed-app`):
Flask + Google Sheets (gspread, service account) + Nedarim Plus hosted
payment + Render hosting. It is a standalone app, not a code dependency on
that repo.

## Stack

- Flask (routes + templates)
- Google Sheets via `gspread` + a service-account credential
- Nedarim Plus hosted payment page (redirect + webhook)
- Gunicorn / Render for hosting

## Project layout

```
app.py            routes: /, /check-phone, /details, /pay, /webhook/nedarim, /api/health
sheets.py         Google Sheets helpers (get_sheets_client, find_registrant, upsert_registrant)
nedarim.py        tier config + Nedarim Plus payment URL builder
templates/        index.html (tier buttons + phone modal), details.html (new-registrant form)
static/           style.css, logo.svg (placeholder)
```

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in the values below
python app.py
```

### Environment variables

See `.env.example`. In short:

- `GOOGLE_SHEET_ID` - the target spreadsheet's ID.
- `GOOGLE_SERVICE_ACCOUNT_JSON` (local) or `GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT`
  (Render / hosts without file uploads) - the service account credential used
  to read/write the sheet. The sheet must be shared with that service
  account's email.
- `NEDARIM_MOSAD_ID` - the institution ID Nedarim Plus assigns per client.
- `NEDARIM_CALLBACK_URL` - the publicly reachable URL for `/webhook/nedarim`.
- `NEDARIM_MONTHLY_RECURRING_PARAM` - recurring-payment (הוראת קבע) param;
  the monthly tier stays disabled in `nedarim.py` until this is confirmed.

## Google Sheet expected columns

`Phone | Name | Tier | Status | Amount | TransactionId | CreatedAt | UpdatedAt`

`upsert_registrant` merges fields into the existing row (matched by phone)
rather than overwriting it, so the payment webhook can't blank out details
collected during registration.

## Open items (blocking full wiring)

1. **Nedarim Plus Mosad ID** - needed to build real payment URLs.
2. **Monthly subscription (הוראת קבע) recurring parameter** - needs the client
   to check the Nedarim Plus admin panel / support for the exact param name
   and value; the monthly tier is implemented but disabled until confirmed.
3. **Google Sheet** - needs to be created, its ID shared with us, and the
   sheet shared with a service account (new or reused from `chesed-app`).
4. **Exact class/session name + logo asset** - `static/logo.svg` is a
   placeholder.
5. **Clarify "weekly"** - a 7-day access window vs. a specific recurring
   weekly class session.
6. **Webhook payload field names** - `Status`, `Id`, `TransactionId`,
   `param1`, `param2` in `app.py`'s `/webhook/nedarim` are best-guess
   placeholders based on Nedarim Plus's general documentation and need to be
   confirmed against real callback payloads.
