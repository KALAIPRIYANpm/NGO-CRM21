"""Database layer: schema, connection, settings and dropdown lists."""
import os, sqlite3, hashlib, secrets, datetime

DB_PATH = os.environ.get("NGO_DB", os.path.join(os.path.dirname(__file__), "..", "data", "ngo.db"))

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT, role TEXT NOT NULL,
  pw_hash TEXT NOT NULL, salt TEXT NOT NULL, active INTEGER DEFAULT 1, must_change INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS lists(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, value TEXT NOT NULL, UNIQUE(kind,value));
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts TEXT, user TEXT, action TEXT, tbl TEXT, row_id INTEGER, detail TEXT);

CREATE TABLE IF NOT EXISTS email_log(
  id INTEGER PRIMARY KEY, ts TEXT, kind TEXT, tbl TEXT, row_id INTEGER, year INTEGER, to_addr TEXT, subject TEXT, status TEXT, error TEXT);
CREATE INDEX IF NOT EXISTS ix_email_dedupe ON email_log(kind, tbl, row_id, year, status);
CREATE TABLE IF NOT EXISTS assets(name TEXT PRIMARY KEY, mime TEXT, data BLOB);
CREATE TABLE IF NOT EXISTS contacts(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT NOT NULL, phone TEXT, email TEXT, organisation TEXT, relation TEXT, city TEXT,
  tags TEXT, msg_optin TEXT DEFAULT 'Y', wishes TEXT DEFAULT 'Y', notes TEXT);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY, campaign_id INTEGER, kind TEXT, rid INTEGER, name TEXT, to_addr TEXT, channel TEXT, status TEXT, error TEXT, provider_id TEXT, ts TEXT);
CREATE INDEX IF NOT EXISTS ix_messages_campaign ON messages(campaign_id);
CREATE TABLE IF NOT EXISTS interactions(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, donor_id INTEGER NOT NULL REFERENCES donors(id), channel TEXT, direction TEXT DEFAULT 'Out',
  summary TEXT NOT NULL, outcome TEXT, next_followup TEXT, owner TEXT);
CREATE TABLE IF NOT EXISTS templates(
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, subject TEXT, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS campaigns(
  id INTEGER PRIMARY KEY, ts TEXT, name TEXT, channel TEXT, segment TEXT, subject TEXT, body TEXT, total INTEGER DEFAULT 0,
  sent INTEGER DEFAULT 0, failed INTEGER DEFAULT 0, status TEXT DEFAULT 'Sending', user TEXT);
CREATE TABLE IF NOT EXISTS compliance(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, due_date TEXT NOT NULL, repeat TEXT DEFAULT 'None', remind_days INTEGER DEFAULT 14, notes TEXT, last_done TEXT);
CREATE TABLE IF NOT EXISTS bank_txns(
  id INTEGER PRIMARY KEY, hash TEXT UNIQUE NOT NULL, date TEXT, amount REAL, type TEXT, narration TEXT, ref TEXT,
  donation_id INTEGER, cash_id INTEGER, imported TEXT);
CREATE TABLE IF NOT EXISTS pledges(
  id INTEGER PRIMARY KEY, ts TEXT, name TEXT NOT NULL, phone TEXT, email TEXT, amount REAL DEFAULT 0, message TEXT,
  status TEXT DEFAULT 'New', ip TEXT);
CREATE TABLE IF NOT EXISTS donors(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT NOT NULL, phone TEXT, city TEXT, donor_type TEXT,
  id_no TEXT, next_followup TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS funds(
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, type TEXT NOT NULL, purpose TEXT, opening REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS projects(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT UNIQUE NOT NULL, place TEXT, lead TEXT, start TEXT, end TEXT,
  target_people INTEGER DEFAULT 0, budget REAL DEFAULT 0, stage TEXT DEFAULT 'Planned',
  funder TEXT, fund_type TEXT, months INTEGER DEFAULT 12, funds_promised REAL DEFAULT 0, my_share_pct REAL DEFAULT 0,
  purpose TEXT, story_person TEXT, story_before TEXT, story_did TEXT, story_after TEXT, story_quote TEXT,
  story_number TEXT, story_number_meaning TEXT, story_next TEXT);
CREATE TABLE IF NOT EXISTS donations(
  id INTEGER PRIMARY KEY, receipt_no TEXT UNIQUE, date TEXT NOT NULL, donor_id INTEGER NOT NULL REFERENCES donors(id),
  purpose TEXT, fund_type TEXT DEFAULT 'General', mode TEXT, reference TEXT, amount REAL NOT NULL,
  receipt_given TEXT DEFAULT 'N', thank_you_sent TEXT DEFAULT 'N', fund_id INTEGER REFERENCES funds(id));
CREATE TABLE IF NOT EXISTS beneficiaries(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, date_joined TEXT, name TEXT NOT NULL, phone TEXT, village TEXT,
  gender TEXT, age_group TEXT, project_id INTEGER REFERENCES projects(id), service TEXT, status TEXT DEFAULT 'Active');
CREATE TABLE IF NOT EXISTS media(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, purpose TEXT DEFAULT 'event', file TEXT NOT NULL, thumb TEXT, mime TEXT, size INTEGER DEFAULT 0,
  project_id INTEGER, activity_id INTEGER, claim_id INTEGER, caption TEXT, consent TEXT DEFAULT 'N',
  taken_at TEXT, uploaded_by INTEGER, uploader TEXT, created TEXT, client_id TEXT);
CREATE INDEX IF NOT EXISTS ix_media_project ON media(project_id, id);
CREATE INDEX IF NOT EXISTS ix_media_claim ON media(claim_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_media_client ON media(client_id) WHERE client_id IS NOT NULL AND client_id<>'';
CREATE TABLE IF NOT EXISTS claims(
  id INTEGER PRIMARY KEY, claim_no TEXT, date TEXT NOT NULL, user_id INTEGER, claimant TEXT, project_id INTEGER, category TEXT,
  amount REAL NOT NULL, description TEXT, status TEXT DEFAULT 'Pending', reviewed_by TEXT, reviewed_on TEXT, remark TEXT,
  paid_on TEXT, cash_book_id INTEGER, client_id TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS ux_claims_client ON claims(client_id) WHERE client_id IS NOT NULL AND client_id<>'';
CREATE TABLE IF NOT EXISTS impact_cards(
  id INTEGER PRIMARY KEY, token TEXT UNIQUE NOT NULL, project_id INTEGER, month TEXT, data TEXT NOT NULL, created TEXT, created_by TEXT,
  revoked INTEGER DEFAULT 0, views INTEGER DEFAULT 0, last_view TEXT);
CREATE TABLE IF NOT EXISTS inbox(
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, channel TEXT NOT NULL, phone TEXT NOT NULL, direction TEXT NOT NULL, name TEXT, text TEXT, kind TEXT DEFAULT 'message',
  provider_id TEXT, read INTEGER DEFAULT 0, delivery TEXT, user TEXT, donor_id INTEGER, contact_id INTEGER);
CREATE INDEX IF NOT EXISTS ix_inbox_thread ON inbox(channel, phone, id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_inbox_provider ON inbox(provider_id) WHERE provider_id IS NOT NULL AND provider_id<>'' AND direction='in';
CREATE TABLE IF NOT EXISTS inbox_threads(channel TEXT NOT NULL, phone TEXT NOT NULL, assignee TEXT, status TEXT DEFAULT 'Open', PRIMARY KEY(channel, phone));
CREATE TABLE IF NOT EXISTS optout(phone TEXT PRIMARY KEY, ts TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS journey(
  id INTEGER PRIMARY KEY, beneficiary_id INTEGER NOT NULL REFERENCES beneficiaries(id), date TEXT NOT NULL, stage TEXT NOT NULL,
  detail TEXT, outcome TEXT, recorded_by TEXT);
CREATE TABLE IF NOT EXISTS commitments(
  id INTEGER PRIMARY KEY, donor_id INTEGER NOT NULL REFERENCES donors(id), amount REAL NOT NULL, frequency TEXT DEFAULT 'Monthly',
  start TEXT NOT NULL, end TEXT, purpose TEXT, status TEXT DEFAULT 'Active', notes TEXT);
CREATE TABLE IF NOT EXISTS partners(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT NOT NULL, sector TEXT, stage TEXT DEFAULT 'Prospect', csr_focus TEXT,
  contact_name TEXT, contact_phone TEXT, contact_email TEXT, expected_amount REAL DEFAULT 0, renewal_date TEXT, last_contact TEXT,
  next_step TEXT, next_step_date TEXT, owner TEXT, backup_owner TEXT, handover_note TEXT, portal_token TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS partner_events(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, partner_id INTEGER REFERENCES partners(id), title TEXT NOT NULL, kind TEXT, project_id INTEGER REFERENCES projects(id),
  venue TEXT, planned_people INTEGER DEFAULT 0, attended INTEGER DEFAULT 0, hours REAL DEFAULT 0, raised REAL DEFAULT 0, status TEXT DEFAULT 'Planned', note TEXT);
CREATE TABLE IF NOT EXISTS tranches(
  id INTEGER PRIMARY KEY, grant_id INTEGER NOT NULL REFERENCES grants(id), due_date TEXT NOT NULL, amount REAL NOT NULL, received_date TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, meeting TEXT, decision TEXT NOT NULL, owner TEXT, due TEXT, status TEXT DEFAULT 'Open', notes TEXT);
CREATE TABLE IF NOT EXISTS policies(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT, adopted_on TEXT, next_review TEXT, owner TEXT, staff_signed TEXT DEFAULT 'No', link TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS trustees(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, role TEXT, since TEXT, term_end TEXT, phone TEXT, email TEXT, id_no TEXT, status TEXT DEFAULT 'Active', notes TEXT);
CREATE TABLE IF NOT EXISTS meetings(
  id INTEGER PRIMARY KEY, date TEXT, kind TEXT, place TEXT, attendees TEXT, quorum TEXT DEFAULT 'Y', agenda TEXT, minutes TEXT, minutes_link TEXT, next_date TEXT);
CREATE TABLE IF NOT EXISTS social_posts(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, platform TEXT, plan_date TEXT, project_id INTEGER, media_id INTEGER, language TEXT DEFAULT 'English',
  caption TEXT, status TEXT DEFAULT 'Idea', owner TEXT, approved_by TEXT, names_ok TEXT DEFAULT 'N', posted_on TEXT, post_link TEXT,
  reach INTEGER DEFAULT 0, reactions INTEGER DEFAULT 0, gifts_amount REAL DEFAULT 0, notes TEXT);
CREATE TABLE IF NOT EXISTS plan_calendar(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, title TEXT NOT NULL, kind TEXT DEFAULT 'Festival', idea TEXT, project_id INTEGER,
  status TEXT DEFAULT 'Idea', owner TEXT, goal REAL DEFAULT 0, raised REAL DEFAULT 0, notes TEXT);
CREATE TABLE IF NOT EXISTS csr_pipeline(
  id INTEGER PRIMARY KEY, company TEXT NOT NULL, kind TEXT DEFAULT 'CSR grant', stage TEXT DEFAULT 'Target', contact TEXT, focus TEXT, project_id INTEGER,
  ask REAL DEFAULT 0, sanctioned REAL DEFAULT 0, decision_by TEXT, next_step TEXT, next_date TEXT, owner TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS official_docs(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT, number TEXT, issued_on TEXT, valid_until TEXT, authority TEXT, location TEXT,
  status TEXT DEFAULT 'Missing', file TEXT, file_name TEXT, mime TEXT, size INTEGER DEFAULT 0, notes TEXT);
CREATE TABLE IF NOT EXISTS outcomes(
  id INTEGER PRIMARY KEY, project_id INTEGER REFERENCES projects(id), title TEXT NOT NULL, unit_cost REAL NOT NULL, per TEXT DEFAULT 'year', description TEXT, active TEXT DEFAULT 'Y');
CREATE TABLE IF NOT EXISTS legacies(
  id INTEGER PRIMARY KEY, donor_id INTEGER REFERENCES donors(id), name TEXT, stage TEXT DEFAULT 'Interested', expected REAL DEFAULT 0, last_contact TEXT, next_contact TEXT, owner TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS risks(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT, likelihood INTEGER DEFAULT 3, impact INTEGER DEFAULT 3, owner TEXT, mitigation TEXT, status TEXT DEFAULT 'Open', review_date TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS incidents(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, kind TEXT, project_id INTEGER REFERENCES projects(id), people TEXT, description TEXT NOT NULL, action_taken TEXT, reported_to TEXT, owner TEXT, status TEXT DEFAULT 'Open', closed_on TEXT);
CREATE TABLE IF NOT EXISTS event_people(
  id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES partner_events(id) ON DELETE CASCADE, name TEXT NOT NULL, hours REAL DEFAULT 0, role TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS activities(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, project_id INTEGER NOT NULL REFERENCES projects(id), activity TEXT,
  village TEXT, people_reached INTEGER DEFAULT 0, volunteers INTEGER DEFAULT 0, spent REAL DEFAULT 0, note TEXT);
CREATE TABLE IF NOT EXISTS team(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT NOT NULL, role TEXT, phone TEXT, pay_type TEXT DEFAULT 'Monthly',
  pay_rate REAL DEFAULT 0, active TEXT DEFAULT 'Y');
CREATE TABLE IF NOT EXISTS attendance(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, team_id INTEGER NOT NULL REFERENCES team(id), attendance TEXT DEFAULT 'P',
  extra_hours REAL DEFAULT 0, advance_paid REAL DEFAULT 0, UNIQUE(date, team_id));
CREATE TABLE IF NOT EXISTS volunteer_log(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, team_id INTEGER NOT NULL REFERENCES team(id), duty TEXT,
  hours REAL DEFAULT 0, km REAL DEFAULT 0, other_paid REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS grants(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE, funder TEXT NOT NULL, project_id INTEGER REFERENCES projects(id),
  start TEXT, end TEXT, sanctioned REAL DEFAULT 0, report_due TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS instalments(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, grant_id INTEGER NOT NULL REFERENCES grants(id), reference TEXT,
  amount REAL NOT NULL, note TEXT, fund_id INTEGER REFERENCES funds(id));
CREATE TABLE IF NOT EXISTS grant_spend(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, grant_id INTEGER NOT NULL REFERENCES grants(id), head TEXT,
  voucher_no TEXT, paid_to TEXT, amount REAL NOT NULL, bill_kept TEXT DEFAULT 'Y', fund_id INTEGER REFERENCES funds(id));
CREATE TABLE IF NOT EXISTS cash_book(
  id INTEGER PRIMARY KEY, date TEXT NOT NULL, voucher_no TEXT, type TEXT NOT NULL, fund_id INTEGER NOT NULL REFERENCES funds(id),
  head TEXT, party TEXT, mode TEXT, amount REAL NOT NULL, note TEXT, source TEXT);
CREATE INDEX IF NOT EXISTS ix_cash_source ON cash_book(source);
CREATE TABLE IF NOT EXISTS budget_lines(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id), line TEXT NOT NULL, grp TEXT DEFAULT 'Programme',
  qty REAL DEFAULT 1, unit_cost REAL DEFAULT 0, times REAL DEFAULT 1);
CREATE TABLE IF NOT EXISTS appeals(id INTEGER PRIMARY KEY, name TEXT NOT NULL, cost REAL DEFAULT 0, raised REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS cashflow_plan(id INTEGER PRIMARY KEY, month TEXT UNIQUE NOT NULL, expected_in REAL DEFAULT 0, expected_out REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS records(
  id INTEGER PRIMARY KEY, record_no TEXT UNIQUE, date TEXT NOT NULL, party TEXT, phone TEXT, address TEXT, project TEXT,
  purpose TEXT, period_ref TEXT, people INTEGER DEFAULT 0, amount REAL DEFAULT 0, received REAL DEFAULT 0, next_date TEXT);
CREATE TABLE IF NOT EXISTS record_lines(
  id INTEGER PRIMARY KEY, record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE, item TEXT, detail TEXT,
  qty REAL DEFAULT 1, unit TEXT, times REAL DEFAULT 1, rate REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS doc_formats(
  name TEXT PRIMARY KEY, title TEXT, line1 TEXT, line2 TEXT, line3 TEXT, show_lines TEXT, show_amounts TEXT,
  sign_left TEXT, sign_right TEXT, sort INTEGER);
CREATE TABLE IF NOT EXISTS results(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id), result TEXT NOT NULL, unit TEXT,
  target REAL DEFAULT 0, achieved REAL DEFAULT 0, people_group TEXT);
CREATE TABLE IF NOT EXISTS project_spend(
  id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id), head TEXT NOT NULL,
  budget REAL DEFAULT 0, used REAL DEFAULT 0, note TEXT);
"""

DEFAULT_SETTINGS = {
 # organisation
 "org_name": "My Trust", "org_head": "", "org_address": "", "org_phone": "", "org_email": "",
 "org_csr1": "", "org_darpan": "", "org_fcra": "",
 "ca_name": "", "ca_firm": "", "ca_phone": "", "ca_email": "", "ca_membership_no": "", "auditor_name": "", "auditor_phone": "", "ca_notes": "",
 "org_reg": "", "org_pan": "", "org_80g": "", "org_12a": "", "org_tagline": "", "org_upi": "",
 # tax info (user's own entries; check with your CA)
 "gst_registered": "No", "gst_pct": "18", "gst_limit": "2000000", "taxable_receipts": "0",
 # rules
 "repeat_gifts": "2", "grant_slow_gap": "0.3", "ending_soon_days": "30", "extra_hour_rate": "60",
 "travel_per_km": "5", "working_days": "26", "fy_start_month": "4", "asof_override": "",
 # donor impact report
 "green_from": "90", "light_from": "70", "yellow_from": "50", "money_ahead": "15", "time_ahead": "20",
 "reporting_period": "", "prepared_by": "", "designation": "",
 # budget tool rules
 "contingency": "0.05", "round_up": "100", "sessions_per_person": "12", "limit_per_person": "2500",
 "funds_available": "0", "reserve_pct": "0.1", "share_by": "By budget", "central_office_cost": "0",
 "admin_limit": "0.15", "reserve_to_build": "0", "running_cost_month": "0", "months_to_keep": "3",
 "camp_people": "0", "camp_days": "1", "camp_venue": "0", "camp_kit_per_person": "0", "camp_food_per_person_day": "0",
 "camp_other": "0", "camp_sponsor": "0", "corpus_rate": "0.07", "cash_opening": "0", "salary_increment": "0.08",
 "tool_project_id": "", "proposal_overhead": "0.1",
 # email + birthday wishes
 "smtp_host": "", "smtp_port": "587", "smtp_security": "starttls", "smtp_user": "", "smtp_password": "", "smtp_from": "",
 "auto_receipt_email": "No", "thanks_message": "Dear {name}, thank you for your gift of Rs {amount} (receipt {receipt}) to {org}. Your support reaches the people we serve. {contact}",
 "digest_auto": "No", "digest_to": "", "digest_hour": "8", "deadline_alerts_auto": "No", "grant_alert_days": "30,15,7",
 "trustee_report_auto": "No", "trustee_emails": "", "report_day": "5", "impact_auto": "No",
 "require_2fa_admin": "No", "wa_app_secret": "", "wa_verify_token": "", "inbound_token": "", "public_url": "", "inbound_stop_reply": "Yes",
 "inbound_stop_text": "You have been unsubscribed and will not get more messages from us. Reply START to subscribe again.", "backup_auto": "Yes", "backup_encrypt": "No", "backup_password": "", "weekly_auto": "No", "weekly_to": "", "weekly_wa_to": "", "weekly_wa_template": "", "commit_remind_auto": "No", "commit_remind_days": "3", "lapse_factor": "1.5", "core_monthly_cost": "0", "reserve_months": "3", "major_donor_min": "50000", "stale_journey_days": "45", "backup_keep": "30", "backup_copy_dir": "", "last_backup": "",
 "public_transparency": "No", "transparency_note": "", "outcome_intro": "Choose what your gift will do.", "brand_product": "NGO Suite", "brand_color": "#0f5e63", "brand_logo_ver": "", "login_note": "Donors, projects, people, grants and accounts in one place.", "setup_done": "No",
 "wa_provider": "None", "wa_phone_id": "", "wa_token": "", "wa_display": "", "wa_lang": "en",
 "sms_provider": "None", "sms_authkey": "", "sms_sender": "", "sms_entity_id": "",
 "twilio_sid": "", "twilio_token": "", "twilio_sms_from": "", "twilio_wa_from": "",
 "custom_url": "", "custom_headers": "", "custom_body": '{"to": "{to}", "message": "{message}"}',
 "donate_page": "No", "donate_message": "Every rupee is used for the people we serve. Pay with any UPI app, then tell us who you are so we can send your receipt.",
 "birthday_auto": "No", "birthday_send_hour": "9",
 "birthday_subject": "Happy Birthday, {name}!",
 "birthday_body": "Dear {name},\n\nWishing you a very happy birthday and a year full of good health and happiness.\nThank you for being part of the {org} family.\n\nWith warm wishes,\n{org}\n{contact}",
}

DEFAULT_LISTS = {
 "doc_kind": ["Registration", "Tax", "CSR and funders", "Foreign funds (FCRA)", "Accounts and audit", "Bank", "Governance", "People and legal", "Programme proof", "Other"],
 "plan_kind": ["Festival", "Awareness day", "Fundraising window", "Company event", "Own event"],
 "pipeline_kind": ["CSR grant", "Employee giving", "Matching gift", "Volunteering", "In-kind", "Sponsorship"],
 "social_platform": ["Facebook", "Instagram", "WhatsApp channel", "LinkedIn", "X", "YouTube"],
 "policy_kind": ["Governance", "Safeguarding", "People", "Finance", "Data and privacy", "Fundraising", "Other"],
 "meeting_kind": ["Board or trustees", "AGM", "Committee", "POSH Internal Committee", "Staff", "Other"],
 "trustee_role": ["Chairperson", "Secretary", "Treasurer", "Trustee", "Member", "Patron"],
 "claim_category": ["Travel", "Food and refreshments", "Materials", "Printing", "Venue or tent", "Fuel", "Phone and data", "Other"],
 "relation": ["Volunteer", "Trustee", "Official", "Media", "Well-wisher", "Partner", "Other"],
 "donor_type": ["Individual", "Company", "Trust or Group", "Member"],
 "purpose": ["General Donation", "Corpus Gift"],
 "mode": ["UPI", "Bank transfer", "Cheque", "Cash"],
 "city": [],
 "stage": ["Planned", "Approved", "Started", "Running", "Reporting", "Closed"],
 "village": [],
 "service": ["Class support", "Skill training", "Health camp", "Saplings", "Home visit", "Scholarship"],
 "activity": ["Class", "Training", "Camp", "Field visit", "Meeting", "Distribution"],
 "age_group": ["Child", "Youth", "Adult", "Elder"],
 "role": ["Project Coordinator", "Field Worker", "Teacher", "Trainer", "Accountant", "Office Helper", "Volunteer"],
 "duty": ["Health camp", "Class help", "Tree planting", "Home visit", "Fund drive", "Office help"],
 "spend_head": ["Salaries", "Training", "Material", "Travel", "Rent", "Office", "Events"],
 "payment_head": ["Salaries", "Programme", "Rent", "Office", "Travel", "Fundraising", "CA and accounts", "Other"],
 "receipt_head": ["Donations", "Grant Received", "Interest", "Other In"],
 "people_group": ["Girls", "Women", "Teachers", "Villagers", "Families", "Elders", "Youth"],
 "result_unit": ["people", "classes", "camps", "meetings", "units"],
 "budget_group": ["Programme", "Staff", "Admin", "Fundraising", "Other"],
 "unit": ["nos", "people", "set", "day", "month"],
 "language": ["English", "Hindi", "Marathi", "Tamil", "Telugu", "Bengali", "Gujarati", "Kannada"],
 "partner_stage": ["Prospect", "Pitched", "Proposal", "Approved", "Active", "Renewal due", "Lapsed"],
 "partner_sector": ["IT and software", "Banking and finance", "Manufacturing", "Pharma and health", "Retail", "Education", "Other"],
 "event_kind": ["Volunteering day", "Skill-based volunteering", "Lunch and learn", "Fundraising drive", "Festival drive", "Field visit", "Stall", "Collection drive", "Payroll giving launch", "Other"],
 "legacy_stage": ["Interested", "Talked to family", "Will being drafted", "Confirmed in writing", "Received", "Declined"],
 "incident_kind": ["Safeguarding concern", "Accident or injury", "Complaint", "Loss or fraud", "Data or privacy", "Other"],
 "risk_category": ["Money", "People", "Programme", "Legal and compliance", "Reputation", "Safety", "Technology"],
 "journey_stage": ["Enrolled", "Assessed", "Service started", "Service given", "Follow-up visit", "Milestone reached", "Outcome achieved", "Referred", "Exited", "Dropped out"],
}

DOC_FORMATS = [
 ("Donation Receipt","DONATION RECEIPT","Received with thanks the amount shown, for the purpose below.","This receipt is for the amount and date shown.","Thank you for your support.","N","Y","Received by","For the organisation"),
 ("Thank You Letter","THANK YOU LETTER","Dear friend, thank you for your support of the work shown below.","Your gift helps us reach the people we serve. We will share our progress with you.","Please stay in touch and visit our work any time.","N","Y","","For the organisation"),
 ("Appeal Letter","APPEAL LETTER","Dear friend, we are writing to ask for your help for the project shown below.","The need is listed here. Any amount you choose to give is welcome.","Please contact us to see the work or to ask any question.","Y","Y","","For the organisation"),
 ("Meeting Notice","MEETING NOTICE","Notice of a meeting of the trustees or members on the next date shown.","The points to be discussed are listed below.","Please attend, or tell us if you cannot.","Y","N","Received by","Secretary"),
 ("Meeting Minutes","MEETING MINUTES","Minutes of the meeting held on the date shown, with the points and decisions below.","Decisions were taken by those present.","To be confirmed at the next meeting.","Y","N","Chairperson","Secretary"),
 ("Utilisation Certificate Format","UTILISATION CERTIFICATE","This is to state that the grant below was received and spent as listed, for the purpose shown.","The balance shown was unspent on the date of this document.","Format only. Use the funder's own form if there is one.","Y","Y","Prepared by","For the organisation"),
 ("Activity Report","ACTIVITY REPORT","Report of the activity shown below: place, people reached and work done.","Spend shown is from our own records.","Photos and attendance are kept on file.","Y","Y","Prepared by","For the organisation"),
 ("Volunteer Letter","VOLUNTEER LETTER","We are glad to welcome you as a volunteer for the project shown below.","Volunteer work is unpaid. Approved travel and food costs are paid back.","Please follow the guidance of the project lead.","N","N","Volunteer","For the organisation"),
 ("Payment Voucher","PAYMENT VOUCHER","Paid the amount shown for the work or goods below.","Bill or receipt attached where available.","Head and fund as noted.","Y","Y","Received by","For the organisation"),
 ("Donor Statement","DONOR STATEMENT","Statement of gifts received from you, as listed below.","Please tell us if anything here differs from your own record.","Thank you for your support.","Y","Y","","For the organisation"),
]

SECRET_KEYS = ("smtp_password", "wa_token", "sms_authkey", "twilio_token", "custom_headers", "wa_app_secret", "wa_verify_token", "inbound_token", "backup_password")
EXTRA_TEMPLATES = [   # (name, channel, provider_template, variables, body): the provider template must be approved in your own provider account
 ("WhatsApp: festival greeting", "WhatsApp", "festival_greeting", "first_name,org", "Dear {first_name}, warm festival wishes from {org}. Thank you for being with us."),
 ("WhatsApp: gift thank-you", "WhatsApp", "gift_thanks", "first_name,org", "Dear {first_name}, thank you for your gift to {org}. Your receipt follows."),
 ("SMS: gift thank-you", "SMS", "", "first_name,org", "Dear {first_name}, thank you for your gift to {org}."),
 ("SMS: event reminder", "SMS", "", "first_name,org", "Dear {first_name}, a reminder of our event from {org}. Details: [fill in]."),
]
DEFAULT_TEMPLATES = [
 ("Festival greeting", "Warm wishes from {org}", "Dear {first_name},\n\nWishing you and your family joy and good health this festive season. Thank you for standing with {org}. Your support keeps our work going.\n\nWith warm regards,\n{org}\n{contact}"),
 ("Appeal for a cause", "Can you help? {org}", "Dear {first_name},\n\nWe are raising support for our current work and your help would mean a great deal. Even a small gift reaches people who need it.\n\nTo give, reply to this message or pay by UPI to {upi}.\n\nThank you,\n{org}\n{contact}"),
 ("We miss you", "We would love to update you", "Dear {first_name},\n\nIt has been a while since we last heard from you, and we wanted to say thank you for your earlier support of {org}. We would be glad to share what has changed since then.\n\nReply here or call us any time.\n\n{org}\n{contact}"),
 ("Event invitation", "You are invited: {org}", "Dear {first_name},\n\nWe would be happy to see you at our next event. Date, time and place: [fill in before sending].\n\nPlease reply to confirm.\n\n{org}\n{contact}"),
 ("Thank you and update", "Thank you from {org}", "Dear {first_name},\n\nThank you for your support. Because of friends like you, we continued our work this month. We will share a fuller report soon.\n\nWith thanks,\n{org}\n{contact}"),
 ("Follow-up after a call", "Following up on our call", "Dear {first_name},\n\nThank you for speaking with us. As promised, here is a short note about how your support can help. Please tell us if you would like more details.\n\n{org}\n{contact}"),
]

def connect():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    return c

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    return h, salt

INDEXES = [("donations", "donor_id"), ("donations", "fund_id"), ("donations", "date"), ("cash_book", "date"), ("cash_book", "fund_id"),
           ("activities", "project_id,date"), ("activities", "client_id"), ("volunteer_log", "team_id,date"), ("beneficiaries", "project_id"),
           ("grants", "project_id"), ("instalments", "grant_id"), ("grant_spend", "grant_id"), ("budget_lines", "project_id"), ("results", "project_id"),
           ("project_spend", "project_id"), ("interactions", "donor_id"), ("interactions", "date"), ("messages", "status"), ("sessions", "user_id"),
           ("audit", "ts"), ("claims", "status"), ("claims", "user_id"), ("records", "date"), ("journey", "beneficiary_id,date"), ("commitments", "donor_id"), ("partners", "stage"), ("partner_events", "partner_id,date"), ("tranches", "grant_id"), ("donations", "partner_id")]

def init_db():
    c = connect()
    c.executescript(SCHEMA)
    # additive migrations for databases created by an earlier version
    for tbl, col, typ in (("donors", "email", "TEXT"), ("donors", "birthday", "TEXT"), ("donors", "wishes", "TEXT DEFAULT 'Y'"),
                          ("team", "email", "TEXT"), ("team", "birthday", "TEXT"), ("team", "wishes", "TEXT DEFAULT 'Y'"),
                          ("team", "bank_account", "TEXT"), ("team", "ifsc", "TEXT"), ("donors", "msg_optin", "TEXT DEFAULT 'Y'"),
                          ("templates", "channel", "TEXT DEFAULT 'Email'"), ("templates", "provider_template", "TEXT"), ("templates", "variables", "TEXT"),
                          ("campaigns", "schedule_at", "TEXT"), ("campaigns", "provider_template", "TEXT"), ("campaigns", "variables", "TEXT"), ("activities", "client_id", "TEXT"), ("users", "totp_secret", "TEXT"), ("users", "totp_pending", "TEXT"),
                          ("donors", "language", "TEXT"), ("donors", "portal_token", "TEXT"), ("donors", "owner", "TEXT"), ("donors", "backup_owner", "TEXT"), ("donors", "handover_note", "TEXT"), ("grants", "owner", "TEXT"), ("grants", "backup_owner", "TEXT"), ("donations", "partner_id", "INTEGER"), ("contacts", "language", "TEXT"), ("users", "totp_last", "INTEGER DEFAULT 0"), ("users", "backup_codes", "TEXT"), ("messages", "delivery", "TEXT")):
        if col not in [r[1] for r in c.execute(f"PRAGMA table_info({tbl})")]:
            c.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {typ}")
    for tbl, cols in INDEXES:      # speed: indexes on the columns lists and reports filter or join by
        have = {r[1] for r in c.execute(f"PRAGMA table_info({tbl})")}
        if have and all(x in have for x in cols.split(",")):
            c.execute(f"CREATE INDEX IF NOT EXISTS ix_{tbl}_{cols.replace(',', '_')} ON {tbl}({cols})")
    c.execute("PRAGMA optimize")
    for k, v in DEFAULT_SETTINGS.items():
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    for kind, vals in DEFAULT_LISTS.items():
        for v in vals:
            c.execute("INSERT OR IGNORE INTO lists(kind,value) VALUES(?,?)", (kind, v))
    for i, f in enumerate(DOC_FORMATS):
        c.execute("INSERT OR IGNORE INTO doc_formats VALUES(?,?,?,?,?,?,?,?,?,?)", (*f, i))
    if not c.execute("SELECT 1 FROM templates").fetchone():
        c.executemany("INSERT INTO templates(name,subject,body) VALUES(?,?,?)", DEFAULT_TEMPLATES)
    for n, ch, pt, var, body in EXTRA_TEMPLATES:
        c.execute("INSERT OR IGNORE INTO templates(name,subject,body,channel,provider_template,variables) VALUES(?,?,?,?,?,?)", (n, "", body, ch, pt, var))
    from . import vault, langpack
    vault.migrate(c)
    langpack.seed_templates(c)
    c.commit()
    c.close()

def get_settings(c):
    from . import vault
    st = {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM settings")}
    for k in SECRET_KEYS:
        if st.get(k): st[k] = vault.unseal(st[k])
    return st

def num(s, k, default=0.0):
    try:
        return float(s.get(k, default))
    except (TypeError, ValueError):
        return float(default)

def asof(s):
    v = (s.get("asof_override") or "").strip()
    if v:
        try:
            return datetime.date.fromisoformat(v)
        except ValueError:
            pass
    return datetime.date.today()
