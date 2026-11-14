# NGO Suite

One working web application that replaces the eight Excel kits of the **NGO & Trust Toolkit**
(Donor & Donation Register, Project & Beneficiary Tracker, Volunteer & Staff Payment, Grant & Utilisation,
Accounts & Fund Report, Documents & Formats, Budget & Fund Toolkit, Donor Impact Report Maker) —
with real logins, one shared database, and the kits' sheets joined up so you type each thing once.

**No installation needed beyond Python 3.9+.** Standard library only (SQLite is built in). Nothing leaves your computer.

## Run it

```bash
python3 seed.py          # optional: load demo data (users admin / accounts / field / viewer, password ChangeMe123)
python3 run.py           # http://127.0.0.1:8000
python3 run.py --host 0.0.0.0 --port 8000   # share on your office network
```
Without the demo data, the first run creates `admin` with a one-time random password printed in the terminal
(you must change it at first sign-in). Set `NGO_ADMIN_PASSWORD=...` to choose it. Data lives in `data/ngo.db`
(override with `NGO_DB=/path/file.db`). Back up from **Admin → Backup & audit**.

## What is inside (kit → module)

| Kit | Pages |
|---|---|
| Donor & Donation Register | Donors (level New / One gift / Repeat, follow-up due), Donations (auto receipt no), A4 receipt, donor statement, Donor insights |
| Project & Beneficiary Tracker | Projects (reach %, used %, days left, flag), Beneficiaries, Activity log (cost per person), Project board (6 stages), activity report |
| Volunteer & Staff Payment | Team, Daily attendance (P/A/H/L), Volunteer log (km + food paid back), Payroll by month (due, advances, net payable) |
| Grant & Utilisation | Grants (used %, time %, pace Slow/Over, report due), Instalments, Grant spend (bill kept), Grant dashboard, utilisation certificate |
| Accounts & Fund Report | Funds (General / Restricted / Corpus), Cash book, Fund dashboard, monthly Trustee report, payment voucher |
| Documents & Formats | Records + lines, the 10 A4 formats (editable wording), your organisation header |
| Budget & Fund Toolkit | Budget lines + all 15 planning tools, proposal budget print, appeals, cash-flow plan |
| Donor Impact Report Maker | Results, project money, story → one-page A4 donor report with the donor's name and share; All-projects page for trustees |

**Joined up:** a donation, grant instalment or grant payment can be posted to a fund; it then appears in the Cash book and fund
balance automatically, and stays in step if you edit or delete it. A restricted gift cannot be posted to a general fund.

## Birthday wishes by email
* Add an **Email** and **Birthday** on a donor or team member (year can be anything; use 2000 if unknown). Untick **Send birthday wishes** for anyone who asked not to be contacted.
* **Birthdays** page (under Fundraising) lists the next 7–366 days, shows who is due today, and lets accounts staff send a wish with one click or send all of today's.
* **Automatic sending:** Settings → *Email and birthday wishes*: fill in your mail server, switch *Send automatically* to Yes and choose the hour. While `run.py` is running, wishes go out once a day. Each person gets at most one wish a year; failures are logged and retried up to 3 times a day.
* Gmail: use `smtp.gmail.com`, port 587, security `starttls`, and an **app password** (not your normal password). Edit the subject and message in Settings (`{name} {org} {contact} {age}`).
* The mail password is stored in your database file and is never shown again in the screens. Only administrators can change mail settings. Use addresses people gave you for this purpose.

## Roles
`admin` everything · `accountant` fundraising, accounts, grants, payroll, planning · `programme` projects, people, attendance, results · `viewer` read-only.

## Safety
Passwords are PBKDF2-hashed; sessions are HttpOnly/SameSite cookies; all SQL is parameterised; all output is escaped;
login attempts are rate-limited; every change is written to an audit log. If you expose it beyond your office, put it behind HTTPS (e.g. a reverse proxy).

## Tests
```bash
python3 -m unittest tests.test_app -v
```
14 API tests cover birthdays and email too (a real SMTP exchange was also checked) and login/roles, cash-book posting, validation, payroll maths, grant pace, trustee-report reconciliation,
impact report, budget maths, printing, CSV import/export and admin functions.

## Notes
* Registration, 80G, FCRA, GST and audit fields are your own entries — check with your CA. Rates and limits are samples until you set them (Settings).
* Import your existing kit data: open a register → **Import CSV**; use the column names shown on the Add form.
* Amounts are stored to 2 decimals as numbers; totals are rounded to whole rupees for display.

## Layout
```
run.py  seed.py  app/{db,spec,logic,server}.py  app/static/{index.html,style.css,app.js,views.js,prints.js}  tests/test_app.py
```
Add a register by adding one `T(...)` entry in `app/spec.py` (fields, list SQL, permissions) plus a table in `app/db.py`; the API, forms, tables, search, CSV and audit follow automatically.

## Automations (Settings → "Automation…", status page: Automations)
The server runs a background check every 10 minutes while it is running. Each item is switched on in Settings; email items need your mail account set up.

| Automation | What it does |
|---|---|
| Receipt + thank-you | Emails the receipt when a donation is saved (donor needs an email). Donations list → **Send…** also gives WhatsApp / SMS links (click-to-send, no paid service). |
| Morning digest | Calls due, receipts and thank-yous pending, donors silent for a year, birthdays, compliance dates; once a day. |
| Deadline alerts | Grant report dates and compliance dates at 30/15/7 days (editable); each alert sent once. |
| Compliance calendar | Your own dates, repeating monthly/quarterly/yearly; "Mark done" rolls to the next date. No tax advice; check dates with your CA. |
| Trustee report / donor impact | Monthly trustee report; quarterly impact email to each donor whose gift went to a project with results. Sent once per period. |
| Bank import | Upload a net-banking CSV. Lines are matched to donations/payments you already recorded (not double counted); re-importing is safe. |
| Payslips | Payroll page → payslip per person, plus a CSV for bank upload (bank account/IFSC kept in Team, finance roles only). |
| UPI QR | On record prints with a balance, on a printable poster, and on the public **/donate.html** page. |
| Donate page + pledges | Public page (off by default). Visitors leave name/phone/email; pledges appear in Pledges; "Make donor" converts them. Rate-limited, with a hidden spam field. Expose it to the internet only if you host the server for that. |
| Field entry (phone) | Big attendance buttons and a new-person form with a duplicate warning. If the network drops, entries wait on the phone and upload later. |
| Daily backup | One copy a day in `data/backups`, old ones pruned, optional copy to a second folder (pen drive / synced folder). |

Not included: QR check-in, and paid WhatsApp/SMS sending.

## White label and communication
**Admin → Branding & setup**: your software name (shown instead of "NGO Suite"), a line under it on the login page, main colour, logo and organisation details. Applied to the login page, menu, browser tab, printed documents (logo), emails (name and colour) and the public Donate page. A "finish setup" banner shows on the admin dashboard until you mark setup complete. Logos must be real PNG/JPG/WEBP/GIF files under 300 KB (SVG is refused for safety) and are stored inside the database, so backups include them.

**Follow-ups** (Fundraising menu): everyone with a follow-up date due in the next 7 days. Log a contact, WhatsApp, call, view the timeline, snooze a week, or clear. **Contact log** records every call, visit and message; the latest entry's follow-up date becomes the donor's next follow-up automatically (so it shows on the board and in the morning digest). **Timeline** (button on each donor) shows gifts, contacts and emails together.

**Send messages**: pick a group (all, gave in last 90 days, lapsed, repeat, big donors, by city, never gave), pick or write a template, then send an email to everyone (runs in the background, recorded under Earlier sends, ends with a "reply STOP" line) or make a one-tap WhatsApp list (each tap is saved to the Contact log). Donors with "Send greetings and updates by email" set to No are never included. Up to 1000 emails per send. **Message templates** are editable.

## Official-number WhatsApp and SMS broadcast
**Communicate → Broadcast** sends one message to many people by official WhatsApp, SMS or email, with a live phone preview, merge fields ({first_name} {name} {org} {contact} {upi}), scheduling, and per-person results (retry failed, cancel scheduled). **Contacts** holds non-donors (volunteers, officials, media) with groups; add them one by one or with Import CSV. Audience choices: donor segments, all contacts, a contact group, or everyone. People are included only if they have a valid number/email and have not been marked "No" for WhatsApp/SMS (or emails). Donors who receive a broadcast get an entry in their timeline.

**What you must set up yourself (the software cannot do this for you):**
- *WhatsApp from your official number* needs the WhatsApp Business Platform (Meta Cloud API): phone number ID + access token, and Meta-approved message templates for anyone who has not messaged you in the last 24 hours. Alternatively Twilio, or any provider through the Custom option.
- *SMS in India* needs DLT registration (sender ID and templates). With MSG91 enter the DLT template ID on the template.
- Connect them in **Admin → Settings → Official WhatsApp and SMS**, then use "Save, then send a test". Keys are stored in the database file, never sent back to the browser, and blank fields keep the saved value.

Honest limits: the provider adapters were tested against a simulated provider, not live accounts, so send a test message before a real broadcast. "Accepted by provider" is not the same as delivered or read; those receipts are in your provider's dashboard. Incoming replies (including STOP) are not received by this software yet: mark opt-outs on the person's record. Provider fees are charged by your provider.

## Field app, photo and video capture (v5)

Open **Overview > Field app (phone)** on a phone. Big buttons for: log an activity with photos and video, attendance and new people, expense claim with a bill photo, and the gallery.

- **Install it.** Browsers offer "Install app" / "Add to Home Screen" (iPhone: Share, then Add to Home Screen). The app opens full screen with your brand colour, and the app files open even with no network. Limit: if the app is started with no network at all, it shows a "No network" screen (you cannot sign in or log entries from it); entries can be made offline only when the app was already open and signed in when the signal dropped. Browsers only allow installing and the camera over HTTPS or `127.0.0.1`: see `docs/HTTPS.md`.
- **Capture.** Take a photo or record a video with the phone camera, or choose existing ones. Photos are shrunk on the phone to about 1600 px before upload (a few hundred KB instead of 5 MB) and always saved as JPEG; a small preview is made for the gallery.
- **Weak network.** Everything is saved on the phone first (IndexedDB) and uploaded in the background: when the network returns, when the app is open, and every minute. A lost reply never makes a duplicate (each item carries an id the server remembers). Items the server refuses (for example a file that is too big) stay visible with a Retry/Discard button. Waiting items belong to the person who made them; another user of the same phone does not upload them.
- **Limits.** Photo 8 MB, video 60 MB (record at 720p or a short clip). Videos are not re-compressed. If the browser cannot keep data (private browsing), the app warns you to stay online until the upload finishes.
- **Privacy.** Every photo has a consent flag (default: not confirmed). View-only users see only items marked "Everyone shown agreed". On the server, EXIF/XMP/IPTC (GPS position, camera serial, photographer name) is removed from every JPEG. Video files are stored as recorded; **location tags inside a video are not removed**, so turn off location tagging in the phone's camera settings if that matters.
- **Storage.** Files live in `data/media/<year>/<month>/` under random names and are served only to signed-in users who are allowed to see them (never as plain web files). Videos stream with seeking. Back up the `data/` folder to keep them: the database backup (Admin > Backup) holds the records, not the photo files.

### Expense claims
Field staff photograph a bill and send a claim. Finance opens **Accounts > Expense claims**, checks the bill, approves or rejects (rejection needs a reason), then pays: choose the fund and the payment posts to the Cash Book as a voucher. The person who made a claim can never approve or pay it (an administrator's own claim needs another finance user). Bills are visible only to the claimant, finance and administrators.

## Security (v5)

- **Two-step sign-in.** Any user can turn it on from the **Security** button (top right): scan a QR with Google Authenticator, Microsoft Authenticator, Authy or similar, and save the 8 one-time backup codes. Codes follow RFC 6238 (tested against the standard test vectors); a code cannot be used twice; 5 wrong codes cancel the attempt. Administrators can require it for all administrators (Settings > Security) and can reset a user who lost their phone (Admin > Users).
- **Provider keys encrypted at rest.** The WhatsApp/SMS tokens, SMS key, custom headers and the mail password, and each user's authenticator secret, are stored encrypted. The key is in `data/secret.key` (or the environment variable `NGO_SECRET_KEY`). Honest description: this is a standard-library construction (HMAC-SHA256 as a stream cipher with an HMAC tag, encrypt-then-MAC), not AES. It protects a copied database file or backup. It does not protect against someone who can read both the database and the key file on the server. **Back up `secret.key` separately and keep it away from the database backups.** If you restore a backup on another computer without the key, the saved provider keys read as empty and must be typed in again (nothing else is affected).
- **Sessions.** Changing a password signs out every other device. Turning two-step on, an admin resetting a password or two-step, and **Sign out everywhere** also end sessions. Sign-ins, failed sign-ins and these events appear in the audit log.
- **HTTPS.** See `docs/HTTPS.md` for Cloudflare Tunnel or Caddy. Behind HTTPS, cookies get `Secure` and the browser gets HSTS.
- **Speed.** Pages and data are compressed (gzip), static files use ETag so a phone downloads nothing when unchanged, and database indexes were added for common lists.

### Not covered yet (be aware)
Backups are not password-encrypted. Lists load up to 5000 rows at once (the photo gallery is paged, but donors, donations and similar registers are not), so very large registers will feel slower. The database is SQLite: fine for one organisation with a few dozen people at once, not for hundreds of simultaneous users. Replies from donors to WhatsApp/SMS are not received (there is no inbound inbox or STOP handling). Provider integrations (WhatsApp/SMS) were tested against a simulated provider, not live accounts. Retention rules for personal data (for example under India's DPDP Act) are not automated.

## Impact cards and the audit/80G pack (v6)

### Impact cards (Reports > Impact cards)
Pick a project and a month. The card is built from what the field logged: people reached, activities, volunteer places, money spent and cost per person, progress against the project's results, up to four photos and one short story you write. Finance publishes it and gets a private link (`/card.html?t=…`) that works on any phone with no sign-in; then **Send to donors…** opens the Broadcast composer with the link already in the message (choose WhatsApp, SMS or email and who receives it; opt-outs are respected as usual).
- Only photos marked "everyone shown agreed" can be chosen, and only from that project and month. If consent is withdrawn later, the photo disappears from the live card immediately.
- The card shows no donor names, staff names or other records. The link is long and unguessable, can be switched off at any time, and counts how many times it was opened. The numbers are frozen when you publish.
- Field staff can preview a card; only an administrator or the accounts officer can publish one.
- Photos are served only for the card's own chosen photos. Anyone holding the link can see the page and forward it.

### Audit and 80G pack (Accounts > Audit and 80G pack)
Choose the financial year (start month follows Settings). You get:
- **Readiness check:** organisation PAN/12A/80G/registration numbers filled in, donors without PAN or ID, cash gifts above Rs 2,000 (generally not deductible under 80G), receipts not yet given, grant payments with no bill kept, expense claims without a bill photo or still waiting. Each item links to where to fix it.
- **Audit pack (zip):** donation register, cash book, fund summary (opening, receipts, payments, closing), grant instalments and spend, expense claims with approver and payment entry, the bill photos, and a draft utilisation statement per grant.
- **80G donor statement:** one printable page per donor per year with PAN/ID, every receipt and the total, with a warning where cash gifts are over the limit.
- **Utilisation statement:** funds received, used by head, balance, bill warnings, and a signature block for your CA.
Add your organisation PAN, 12A and 80G numbers under Settings > Your organisation. **These are drafts built from your own records, not legal or tax advice.** Rules such as the cash limit and the wording of 80G acknowledgements change; have your Chartered Accountant review and certify before anything is issued or filed. The software does not file anything (no Form 10BD/10BE, no FCRA returns) and does not check that your 80G/12A approvals are valid.

## Reply inbox and STOP handling (v7)

**Communicate > Inbox** shows replies from donors and contacts, grouped by person, with an unread count in the menu and on the dashboard. You can reply, assign a conversation to a colleague, mark it done (a new message reopens it), open the donor or contact record, or save an unknown number as a contact (saved as *not OK for broadcasts*: writing to you is not agreeing to broadcasts). Only administrators and the accounts officer see the inbox.

**STOP is applied at once and remembered.** If the whole message is STOP, STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT or OPT OUT (any capitals or punctuation), the person is switched off for WhatsApp/SMS in their donor and contact records, their number is added to an opt-out list that every broadcast checks (even for people added to your records later, and even for campaigns scheduled before they replied), and they get an automatic confirmation (you can switch that off). START, UNSTOP, SUBSCRIBE or RESUME switches them back on. A sentence that merely contains "stop" does not count.

**Connecting your provider** (Settings > Receiving replies, with step-by-step help on that page):
- *Meta WhatsApp Cloud API:* give Meta the Callback URL and a Verify token, subscribe to "messages", and paste the App Secret. Every call is checked against Meta's signature; unsigned calls are refused. Delivery receipts (sent, delivered, read) are recorded too.
- *Twilio (WhatsApp or SMS):* set the incoming-message webhook to your address. Calls are checked with Twilio's signature, which depends on the exact public address, so **Public web address** must match what you gave Twilio.
- *Any other provider:* a secret link (`/api/hook/generic?token=…`) accepts JSON or form posts with the sender (from, mobile, sender or phone) and the text (text, message or body). Field names differ between providers, so test with one message.
- Your provider must reach the software over the internet: follow `docs/HTTPS.md` first.

Limits to know: WhatsApp allows a free-text reply only within 24 hours of the person's last message (the inbox says so and blocks it; use an approved template from Broadcast after that). Indian DLT SMS providers (such as MSG91) generally do not allow free-text SMS replies, so SMS replies work through Twilio or a custom provider only. Photos, voice notes and other media from WhatsApp appear as a placeholder line; open them in your WhatsApp app. STOP words are recognised in English only; other languages arrive as ordinary messages for a person to handle. This was tested against simulated provider calls (with real signature checks), **not** against live Meta, Twilio or MSG91 accounts, so run a test with your own number first. Message text is stored in the database as readable text (only provider keys and authenticator secrets are encrypted), so treat the database and its backups as personal data.

## Version 8: donor care, journeys, protected backups

* **Password-protected backups and restore** (Admin > Backup & restore). File type `.ngobk`: PBKDF2 key from your password, HMAC-SHA256 stream cipher with a tamper-check tag (standard-library construction, not AES). It includes the server key so a restore on a new computer brings back saved mail/WhatsApp keys. **Photos and videos (`data/media`) are not inside**: copy that folder separately. A lost password cannot be recovered. Turn on locked daily backups in Settings > Automation. Restore needs your admin password, the word RESTORE, saves a safety copy first, signs everyone out, and returns passwords to those in the backup. Plain `.db` backups also restore.
* **Regional languages**: phone (field) screens and donor message templates in Hindi, Marathi, Tamil, Telugu, Bengali, Gujarati, Kannada. Buttons and main labels are translated; long help sentences stay English. **Have a native speaker read the wording once** (`app/static/lang.js`, `app/langpack.py`). Set each donor's preferred language; broadcast can target a language.
* **Beneficiary journey**: Journey steps register plus a timeline per person, progress funnel by project, and a "needs a visit" list (days set in Settings).
* **Manager weekly summary**: on screen, and by email (and optional WhatsApp template) on Mondays when switched on.
* **Offline start**: after one normal sign-in as admin or field staff, the phone app opens without signal and queues entries. Sign out erases the offline snapshot. Uploading still needs a valid sign-in.
* **Donors slipping away**: compares each donor with their own giving rhythm. WhatsApp buttons open your own phone's chat with the message ready (only for donors who agreed).
* **Giving promises**: monthly/quarterly/half-yearly/yearly promises matched to donations; optional email reminders.
* **Find duplicates**: donors and people served, by phone, email or very similar name in the same place; merge keeps all history; every merge is audited.
* **Funder report (CSR)**: a draft project report for a company funder (consented photos only). Read it and use the funder's own format if required.
* **Audit trail**: searchable and filterable, CSV export, per-record history (administrators only).


## Version 9: company partners, cash forecast, board pack

New pages (look for the orange "New" pills):

- **Fundraising → Company partners.** Pipeline from Prospect to Renewal, with owner, backup, next step and renewal date. Flags show a near renewal, an overdue next step, 60 days of no contact, or no owner or backup. Choose the company on a donation to record gifts that came through it. A **company page** (private link, can be switched off) shows that company only its own gifts, events and volunteer hours.
- **Fundraising → Office events.** Volunteering days, talks, drives and visits: who came, hours, money raised. **Thank-you note** writes a ready note for the company.
- **Fundraising → Key relationships.** Major donors, active companies and funders, with owner, backup and handover note. Shows how much value sits with each person, and who has no cover.
- **Grants → Expected payments.** Money a funder promised on a date. Overdue payments are flagged and appear in the weekly summary.
- **Planning → Cash forecast.** Twelve months ahead: giving promises, expected funder payments and your Cash Flow Plan lines against your monthly cost. Restricted and corpus funds are taken out to show free cash. Set core monthly cost, reserve months and the major-donor line in Settings → Money planning.
- **Planning → Board pack and Board decisions.** One printable page for trustees (money, forecast, funder payments, company pipeline, open decisions, statutory dates, and the things to look at first). Open decisions carry forward until marked Done.

Limits to know: the forecast only knows what you have entered and is not a promise; events record totals (people and hours), not each person; the company page is a simple read-only page, not a login; the board pack is a draft to check against your accounts.

### Design refresh (v9b)

Every page uses one design system: cool grey paper, white surfaces, your brand colour as the single accent, sentence-case labels, and ledger-style tables (strong rule under the header, money in aligned figures, double rule above totals). Sign-in, menu, forms, dialogs, charts, the field app and printing are all covered, and phones get a compact top menu and two-column figures. Your logo and brand colour (Branding & setup) still recolour the menu, buttons and links. All styling lives in `app/static/style.css`; the last section is the new design system.

## Sample data (v9c)
`python3 seed.py` now also loads a worked example: donor Asha Verma (monthly UPI promise, owner and backup, handover note), four sample company partners with an office event, two overdue/upcoming funder payments, two board decisions, and four reply-inbox messages (receipt request, sponsor question, event confirmation, STOP). Names are made up; delete them before real use.

Sample data now fills every page except photos, logo and login sessions (pledges, expense claims, bank lines, a broadcast, journey steps, an impact card and email log are included). A 80-second walkthrough video is shipped separately as ngo-suite-walkthrough.mp4.

Sample data now also includes six made-up photos in Photos and videos, a sample logo, and a duplicate donor pair for Find duplicates (files: sample_assets.py, loaded by seed.py).

## Sample data mode (v9c)
`python3 run.py --demo --port 8021` (or START-DEMO-WINDOWS.bat) runs the app on data/demo.db and loads sample data on first start. Your real database (data/ngo.db) is separate. `seed.py` refuses to load into a database that already has data, which is why older installs did not show the sample rows.

## v10 additions
- Donor "Your giving" page (private link per donor), public transparency page (off until you switch it on in Settings), sponsor-an-outcome choices on the Donate page.
- Bulk import with a "Check file first" step and blank templates; legacy pipeline; risk map and register; incident register; yearly compliance check (a prompt list, not legal advice); per-person attendance for office events.
- Display button: dark mode and accent colour. Help and page guide in the menu. Hindi and Marathi menus and buttons (need review by a native speaker).
- Hosting: see `docs/DEPLOY.md`, `Dockerfile`, `docker-compose.yml`, `deploy/`.

## v11 additions
- New Governance pages: Policy register (with "Add the usual policies"), Trustees and members, Meetings and minutes.
- Settings, "Your CA and auditor": all blank until you have the details. Compliance calendar dates can also be left blank until your CA confirms them; blank items are never counted as overdue.
- Every page has a "Why we need this page" panel (what it is for, and when to use it). Close it with the arrow; it stays closed for that page. The wording is in `app/static/v11.js` and can be edited.

## v12 additions: social media planner
- **Post ideas** (Communicate): lists events coming up, events just done, activities with a consented photo, and projects ending soon; drafts a caption in English, Hindi or Marathi from your own numbers (have a native speaker read the Hindi and Marathi wording).
- **Social posts**: a plan with status Idea, Drafted, Approved, Posted. A different person must approve; a photo must have consent; a post that names a donor or beneficiary is blocked unless you tick that they agreed. Record reach and gifts after posting.
- Nothing is posted from the software. Publish with Meta Business Suite, Buffer or the app itself.

## v13 additions: yearly plan
- **Yearly plan** (Planning): the next 12 months in one list: festivals and giving windows, company next steps and decision dates, compliance dates. "Prepare now" appears four weeks before a campaign.
- **Festival calendar**: "Add the standard calendar" adds about 22 festivals, awareness days and giving windows from November 2026 to October 2027. Festival dates differ by region and source: confirm each on a panchang.
- **Company funding pipeline** (Fundraising): CSR grants, employee giving, matching gifts, volunteering. Move each company from Target to Approached, Pitched, Due diligence, Plan approval, Sanctioned, Disbursing, Reporting, Renewal.

## v14: Official documents and CSR proposal
- **Official documents** (Documents menu): a library of registration, tax, CSR, audit and governance papers. Press "Add the standard list" once. For each paper note the number and expiry, and attach the scan (PDF, JPEG, PNG or Word, up to 10 MB). State shows Missing, Applied, Have, Expires soon (60 days) or Expired. Admin and accounts only. Files are stored under the media folder `docs/`.
- **CSR proposal** (Reports menu): pick a project and a company, and a printable draft opens, built from your activities, beneficiaries, results, budget, registrations and trustees. Yellow brackets are what only you can write. It is a draft: fill every bracket, check figures with your CA, and use the company's own format if it has one.
- New settings: CSR-1 number, NGO Darpan ID, FCRA number.
- Limits: the proposal wording is a general template and Schedule VII wording should be checked against the current Act; attached files are stored as-is and are not scanned for viruses beyond file-type checking.

## v14.1: Alerts bell
An "Alerts" button with a count sits at the top right of every page. It lists, for the next 14 days and anything overdue: birthdays, events, festivals and campaigns not yet confirmed, programme start and end dates, compliance dates, expiring official documents, grant reports, meetings, company next steps and donor calls due. What you see depends on your role (viewers and field staff see events and programmes only). It is checked when a page loads; it does not send email (the daily digest does that).

## v15: Interface and speed pass
- **Header:** Alerts bell plus one account menu (language, password, display, two-step, sign out) instead of six small buttons.
- **Phones:** every register turns into one card per record under 640 px wide, so nothing is cut off or needs sideways scrolling.
- **"Why we need this page"** opens the first time you visit a page, then stays collapsed; click it to open again.
- **Large registers:** lists load the latest 5,000 records. Search now looks through all records on the server when a register is larger than that, and the page says so.
- Measured on 30,000 donations: dashboard 35 ms, list 45 ms, first sign-in about 0.8 s on the local machine. The slowest page was the yearly compliance check at about 0.13 s.
