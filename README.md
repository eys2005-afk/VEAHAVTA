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
- **`NEDARIM_API_VALID`**: the value from the client's original email
  (`da772`) turned out to be wrong/stale - the real, current value is
  shown live on the Nedarim Plus back-office (reports.matara.pro) under
  "מפתחות API" and does **not** match what was emailed. If auth ever
  fails again ("סיסמת אימות לא תקינה"), check there first, not the email.
- **`FinishTransaction2` payload shape**: the official PostNedarim table
  (client-supplied PDF, `debitiframe2.pdf`) states every parameter in it
  is mandatory to include, **even empty** ("חובה לרשום את כל הפרמטרים, גם
  אם הם ריקים"). Omitting unused ones (`Zeout`/`Street`/`City`/`Groupe`/
  `Comment`) made Nedarim Plus reject every transaction with a misleading
  "נא לציין שם פרטי ומשפחה" error - `build_iframe_transaction()` now sends
  the full 19-field set field-for-field, matching the table exactly.
- **`/webhook/nedarim` Content-Type**: a real callback (confirmed via the
  documented source IP) was being dropped with a 400 - Nedarim Plus sends
  the callback body as JSON without a `Content-Type` Flask recognizes as
  `application/json`, so `request.form`/`request.args`/plain `get_json()`
  all came back empty. Fixed with `get_json(force=True)`.
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

1. **End-to-end real charge still not confirmed successful** - as of
   2026-08-11, `ApiValid` is now correct and `FinishTransaction2` sends
   the full documented field set (see "Resolved"), which should clear the
   two errors seen so far ("סיסמת אימות לא תקינה", then "נא לציין שם פרטי
   ומשפחה"). Still needs one real test charge (via `NEDARIM_TEST_AMOUNT=1`,
   see `.env.example`) to confirm a card charge actually completes and
   `/webhook/nedarim` receives a `Status: "OK"` callback that updates the
   Sheet - `app.py` logs the full raw payload of every webhook hit to
   confirm the exact success-case field names once that happens.
2. **`NEDARIM_CALLBACK_IP` (`18.194.219.73`) logged but not enforced** -
   confirmed accurate against real callback hits; worth enforcing once
   the success case above is also confirmed, to guard against spoofed
   callbacks.
3. **Monthly subscription (הוראת קבע) price + recurring parameter** - price
   wasn't given in the client's brief; the docs show a `PaymentType: 'HK'`
   mode with its own `Amount`/`Tashlumim` meaning (monthly amount / number
   of months), which `build_iframe_transaction()` already switches to for
   the monthly tier - still disabled until the price is confirmed.
4. **Exact class/session names** - the client sets these weekly from
   `/admin` now; no code change needed once they start filling it in.
