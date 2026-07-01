# ואהבת (VEAHAVTA)

QR-code landing page for a class called "ואהבת". Flow:

1. Visitor scans a QR code and lands on `/`.
2. They pick a tier and enter their phone number.
3. Returning registrants skip straight to payment; new registrants fill in
   a short details form (`/details`).
4. `/pay` renders a page with Nedarim Plus's payment form embedded in an
   iframe (chosen over a full-page redirect so the visitor never leaves the
   ואהבת page) - no card data ever touches this server.
5. Nedarim Plus calls back `/webhook/nedarim` on completion, and the
   registrant's row in Google Sheets is updated with payment status.

This mirrors the architecture of the client's other project (`chesed-app`):
Flask + Google Sheets (gspread, service account) + Nedarim Plus hosted
payment + Render hosting. It is a standalone app, not a code dependency on
that repo.

## Stack

- Flask (routes + templates)
- Google Sheets via `gspread` + a service-account credential
- Nedarim Plus hosted payment form, embedded via iframe + webhook
- Gunicorn / Render for hosting

## Project layout

```
app.py            routes: /, /check-phone, /details, /pay, /webhook/nedarim, /api/health
sheets.py         Google Sheets helpers (get_sheets_client, find_registrant, upsert_registrant)
nedarim.py        tier config + Nedarim Plus payment param/URL builders
templates/        index.html (tier buttons + phone modal), details.html (new-registrant
                  form), pay.html (embedded Nedarim Plus iframe)
static/           style.css, logo.jpg (the client's real logo)
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
  Confirmed real value for this client: `7016996`. No `ApiValid` key is
  needed - verified by live testing against the real Mosad ID.
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

## Resolved

- **Nedarim Plus Mosad ID**: `7016996`, confirmed real and working. No
  `ApiValid` needed. The path/param casing matters: `online/?mosad=...`
  (lowercase) works; `Online/?Mosad=...` (capitalized) throws a server
  error on Nedarim Plus's side.
- **Google Sheet**: created (`ואהבת - נרשמים`), Hebrew header row added,
  shared with the `veahavta-sheets@veahavta-app.iam.gserviceaccount.com`
  service account (share itself not yet independently confirmed - will be
  proven once the app actually writes to it).
- **Logo**: real logo added at `static/logo.jpg`.

## Open items (blocking full wiring)

1. **iframe/postMessage handshake not yet live-tested** - `templates/pay.html`
   embeds `https://matara.pro/nedarimplus/iframe/?language=he` and posts a
   `{Name: 'Set', Value: {...}}` message to it, reconstructed from patterns
   in other live Nedarim Plus integrations (not official docs). Unlike the
   plain redirect form in `nedarim.py` (verified working end-to-end against
   the real Mosad ID), this needs to be tested live once deployed.
2. **Webhook payload field names** - `Status`, `Id`, `TransactionId` in
   `app.py`'s `/webhook/nedarim` are still best-guess placeholders. The
   fastest way to confirm them: make one real ₪1 charge (redirect form,
   `CallBack` pointed at something like webhook.site) and inspect what
   Nedarim Plus actually sends, then refund/void it via their admin panel.
3. **Monthly subscription (הוראת קבע) price + recurring parameter** - price
   wasn't given in the client's brief, and the recurring-payment param name
   needs the client to check with Nedarim Plus support; the monthly tier is
   implemented but disabled until both are confirmed.
4. **Exact class/session name** - `CLASS_NAME` env var is still a placeholder.
5. **Clarify "weekly"** - a 7-day access window vs. a specific recurring
   weekly class session.
6. **Deploy to Render** - connect the repo, set env vars (`GOOGLE_SHEET_ID`
   is `1xHYATMbKU_4WyKPvx2ppjRs8xsHhWs2dnWi5-OEEa8E`), then set
   `NEDARIM_CALLBACK_URL` to the live `/webhook/nedarim` URL once known.
