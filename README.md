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
- `NEDARIM_API_VALID` - per-institution API key required alongside Mosad
  (confirmed by cross-referencing several other live Nedarim Plus
  integrations; not yet verified against this client's own account).
- `NEDARIM_CALLBACK_URL` - the publicly reachable URL for `/webhook/nedarim`.
- `NEDARIM_MONTHLY_RECURRING_PARAM` - recurring-payment (הוראת קבע) param;
  the monthly tier stays disabled in `nedarim.py` until this is confirmed.
- `CLASS_NAME` - the class/session name shown under the logo on the landing
  page; still pending from the client (see Open items).

## Pricing (per the client's brief)

| Tier    | Price | Notes                                   |
|---------|-------|------------------------------------------|
| Single  | ₪30   |                                          |
| Weekly  | ₪50   | "Weekly" scope still needs clarifying    |
| Monthly | TBD   | Disabled until price + recurring param confirmed |

## Registrant form fields

Phone (collected up front) → on first registration: full name, email,
marital status (רווק/ה - נשוי/אה).

## Google Sheet expected columns

Row 1 of the sheet must contain these Hebrew headers, in this exact order
(columns A-J) - `sheets.py`'s `HEADER_LABELS` maps them back to the internal
English field names the code uses:

`טלפון | שם | אימייל | מצב משפחתי | מסלול | סטטוס | סכום | מזהה עסקה | נוצר בתאריך | עודכן בתאריך`

(internally: `Phone | Name | Email | MaritalStatus | Tier | Status | Amount | TransactionId | CreatedAt | UpdatedAt`)

`upsert_registrant` merges fields into the existing row (matched by phone)
rather than overwriting it, so the payment webhook can't blank out details
collected during registration.

## Open items (blocking full wiring)

1. **Nedarim Plus Mosad ID + ApiValid** - needed to build real payment URLs.
   Once available, the fastest way to nail down the webhook payload shape is
   a real ₪1 charge: point `CallBack` at a capture endpoint (e.g.
   webhook.site, or a temporary logging route), make one real-card charge,
   inspect the payload, then refund/void it via the Nedarim Plus admin panel.
2. **Monthly subscription (הוראת קבע) price + recurring parameter** - price
   wasn't given in the client's brief, and the recurring-payment param name
   needs the client to check with Nedarim Plus support; the monthly tier is
   implemented but disabled until both are confirmed.
3. **Google Sheet** - needs to be created, its ID shared with us, and the
   sheet shared with a service account (new or reused from `chesed-app`).
4. **Exact class/session name + logo asset** - `CLASS_NAME` env var and
   `static/logo.svg` are placeholders.
5. **Clarify "weekly"** - a 7-day access window vs. a specific recurring
   weekly class session.
6. **Webhook payload field names** - `Status`, `Id`, `TransactionId` in
   `app.py`'s `/webhook/nedarim` are best-guess placeholders (informed by
   other live Nedarim Plus integrations, not this client's own account) and
   need to be confirmed against a real callback payload - see item 1.
