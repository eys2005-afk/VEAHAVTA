# ואהבת (VEAHAVTA)

QR-code landing page for a class called "ואהבת". Flow:

1. Visitor scans a QR code and lands on `/` ("כמה טוב שבאת!").
2. They pick a tier and enter their phone number.
3. Returning registrants see a "כיף שהגעת שוב!" greeting and skip straight
   to payment; new registrants see "ברוך הבא!" on a short details form
   (`/details`).
4. `/pay` embeds Nedarim Plus's payment form in an iframe (per their
   official iframe integration guide - see "Resolved") so the visitor never
   leaves the ואהבת page - no card data ever touches this server.
5. Nedarim Plus calls back `/webhook/nedarim` on completion, and the
   registrant's row in Google Sheets is updated with payment status.

The client manages the site themselves from `/admin` (password-protected):
editing which class runs on each day of the week, toggling a free-mode
promo, adding a temporary workshop tier, and viewing registrants.

This mirrors the architecture of the client's other project (`chesed-app`):
Flask + Google Sheets (gspread, service account) + Nedarim Plus hosted
payment + Render hosting. It is a standalone app, not a code dependency on
that repo.

## Stack

- Flask (routes + templates)
- Google Sheets via `gspread` + a service-account credential
- Nedarim Plus payment form, embedded via iframe + webhook
- Gunicorn / Render for hosting

## Project layout

```
app.py            routes: /, /check-phone, /details, /pay, /webhook/nedarim,
                  /admin, /admin/login, /admin/logout, /api/health
sheets.py         Google Sheets helpers - registrants (find_registrant,
                  upsert_registrant, get_all_registrants) and site settings:
                  weekly class schedule + free-mode/workshop toggles
                  (get_weekly_schedule, get_site_settings, update_settings)
nedarim.py        tier config (including punch-card "entries") + Nedarim
                  Plus payment param/URL builders
templates/        index.html (tier buttons + phone modal), details.html
                  (new-registrant form), pay.html (embedded Nedarim Plus
                  iframe), checkin.html (punch-card check-in / free
                  confirmation), admin_login.html, admin.html
static/           style.css, logo.png (the client's real logo)
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
  Confirmed real value for this client: `7016996`.
- `NEDARIM_API_VALID` - a separate auth token required by the iframe's
  `FinishTransaction2` message, per Nedarim Plus's official docs. Obtained
  from Nedarim Plus (called `ApiPassword` in their email) - set on Render,
  not committed here.
- `NEDARIM_CALLBACK_URL` - the publicly reachable URL for `/webhook/nedarim`.
- `NEDARIM_CALLBACK_MAIL_ERROR` - optional email Nedarim Plus notifies if
  sending the callback fails; if empty, they email the institution's
  contacts instead.
- `NEDARIM_MONTHLY_RECURRING_PARAM` - recurring-payment (הוראת קבע) param;
  the monthly tier stays disabled in `nedarim.py` until this is confirmed.
- `CLASS_NAME_SUNDAY` .. `CLASS_NAME_SATURDAY` - fallback per-day class name
  if the Sheet-based schedule (edited from `/admin`) is unreachable; then
  `CLASS_NAME`, then a placeholder.
- `ADMIN_PASSWORD` - password for `/admin`. Login is disabled if left empty.

## Admin panel (`/admin`)

Password-protected (`ADMIN_PASSWORD`), lets the client self-serve without
touching Render or GitHub. All settings live in a `הגדרות` tab added
automatically to the same Google Sheet (`sheets.py`'s `get_site_settings`/
`update_settings`); `get_active_tiers()` in `app.py` reads them on every
request, falling back to the plain static tiers if the sheet is unreachable:

- **Weekly class schedule** - one text field per day of the week.
- **Free mode** - a checkbox that zeroes every enabled tier's price (e.g.
  for an Elul opening-month promo). Visitors still go through the normal
  scan/phone flow, but `/pay` skips Nedarim Plus entirely and shows "הפעם
  זה חינם" instead, so they still register and see the app normally.
- **Temporary workshop tier** - name + price + on/off, shown as an extra
  button on the same fixed homepage/QR link (no new link needed per event).
- **Registrants** - a read-only table of everyone who's registered, plus a
  link to open the full Google Sheet directly.

## Pricing (per the client)

| Tier         | Price       | Notes                                        |
|--------------|-------------|-----------------------------------------------|
| Single       | ₪30/evening |                                                |
| Punch card   | ₪75/3 entries | Replaces the old time-based "weekly" tier - see "Multi-visit tracking" below |
| Monthly      | TBD         | Disabled until price + recurring param confirmed |

### Multi-visit tracking (punch cards)

There's no physical scanner or door staff, so the only way the app can
know someone showed up is if they scan the QR code every visit - that part
doesn't go away. What changes is what happens after: paying for a
punch-card tier sets `EntriesRemaining` on their Sheet row (`nedarim.py`'s
`TIERS[...]["entries"]`); scanning again on the *same* tier with visits
left skips Nedarim Plus entirely and just shows a "✓ נרשמת, נשארו לך X
כניסות" confirmation while decrementing the count (`/pay` in `app.py`).
Once it hits zero, the next scan asks for payment again like normal.

## Registrant form fields

Phone (collected up front) → on first registration: full name, email,
marital status (רווק/ה - נשוי/אה).

## Google Sheet expected columns

Row 1 of the sheet must contain these Hebrew headers, in this exact order
(columns A-K) - `sheets.py`'s `HEADER_LABELS` maps them back to the internal
English field names the code uses:

`טלפון | שם | אימייל | מצב משפחתי | מסלול | סטטוס | סכום | מזהה עסקה | כניסות נותרו | נוצר בתאריך | עודכן בתאריך`

(internally: `Phone | Name | Email | MaritalStatus | Tier | Status | Amount | TransactionId | EntriesRemaining | CreatedAt | UpdatedAt`)

`upsert_registrant` merges fields into the existing row (matched by phone)
rather than overwriting it, so the payment webhook can't blank out details
collected during registration.

## Resolved

- **Nedarim Plus Mosad ID**: `7016996`, confirmed real and working.
- **Official iframe protocol**: the client supplied Nedarim Plus's actual
  iframe integration guide (PDF). This resolved several earlier guesses:
  - The plain redirect page (`online/?mosad=...`) does **not** support
    server-side `CallBack` notifications at all - that's only documented
    for the iframe flow. This is why earlier real-money ₪1/₪30 tests via
    the redirect never reached `/webhook/nedarim`, no matter what we
    changed in our own code.
  - The iframe handshake sends **raw JS objects via `postMessage` (not
    `JSON.stringify`'d)**, first `{Name: 'GetHeight'}`, then
    `{Name: 'FinishTransaction2', Value: {...}}` with the transaction
    details - not the `{Name: 'Set', ...}` shape we'd guessed earlier.
  - The response comes back as `{Name: 'TransactionResponse', Value:
    {Status, Message, ...}}` (`Status == 'Error'` on failure).
  - `nedarim.py`'s `build_iframe_transaction()` and `templates/pay.html`
    now implement this documented protocol directly (not a guess).
- **Google Sheet**: created (`ואהבת - נרשמים`), Hebrew header row added,
  shared with the `veahavta-sheets@veahavta-app.iam.gserviceaccount.com`
  service account, and confirmed working (real registrant rows have landed
  in it from live testing).
- **Logo**: real (transparent) logo added at `static/logo.png`.

## Deployed

Live on Render at `https://veahavta-app.onrender.com`, with `GOOGLE_SHEET_ID`,
`GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT`, `NEDARIM_MOSAD_ID`, and
`NEDARIM_CALLBACK_URL` set as environment variables there.

## Open items (blocking full wiring)

1. **iframe protocol implemented but not yet live-tested with `NEDARIM_API_VALID`
   set** - built directly from Nedarim Plus's own documentation (not
   reverse-engineered guesses); now that the client has the real
   `ApiValid`, this needs to be verified in the browser with a real charge.
2. **Webhook payload field names still partially unconfirmed** - `Status`,
   `TransactionId` in `/webhook/nedarim` match a real working integration
   we found (`Status == "OK"` on success), but haven't been confirmed
   against this client's own account yet, since the previous test channel
   (the plain redirect) doesn't support callbacks at all (see "Resolved").
   `app.py` logs the full raw payload of every hit to help confirm this
   once a real charge goes through the iframe. The docs also state Nedarim
   Plus's callback always originates from IP `18.194.219.73` - logged
   (`NEDARIM_CALLBACK_IP` in `app.py`) but not yet enforced; worth adding
   once confirmed to guard against spoofed callbacks.
3. **Monthly subscription (הוראת קבע) price + recurring parameter** - price
   wasn't given in the client's brief; the docs show a `PaymentType: 'HK'`
   mode with its own `Amount`/`Tashlumim` meaning (monthly amount / number
   of months), which `build_iframe_transaction()` already switches to for
   the monthly tier - still disabled until the price is confirmed.
4. **Exact class/session names** - the client sets these weekly from
   `/admin` now; no code change needed once they start filling it in.
