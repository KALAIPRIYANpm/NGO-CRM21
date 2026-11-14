"""Automations: daily digest, deadline alerts, receipt emails, scheduled reports, backups, bank import, payslips, pledges, duplicates.
Everything that sends mail needs SMTP set up in Settings; backups and the rest work without it."""
import csv, io, os, re, shutil, hashlib, datetime, sqlite3, time, threading, zlib, html as _html
from . import db, logic, mailer
from .mailer import EMAIL_RE, MailError

SEND_DELAY = 0.5      # seconds between bulk emails (kind to mail servers); tests set 0
E = lambda x: _html.escape(str(x if x is not None else ""))
money = lambda v: ("-" if (v or 0) < 0 else "") + "₹" + format(int(round(abs(v or 0))), ",")

def _indian(n):
    s = str(int(round(abs(n)))); 
    if len(s) <= 3: return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2: parts.insert(0, head[-2:]); head = head[:-2]
    if head: parts.insert(0, head)
    return ",".join(parts + [tail])
money = lambda v: ("-" if (v or 0) < 0 else "") + "₹" + _indian(v or 0)

def recipients(s, key):
    return [x for x in re.split(r"[,;\s]+", s.get(key, "") or "") if EMAIL_RE.match(x)]

def _rid(addr): return zlib.crc32(addr.lower().encode()) & 0x7FFFFFFF
def _already(c, kind, tbl, rid, year):
    return c.execute("SELECT 1 FROM email_log WHERE kind=? AND tbl=? AND row_id=? AND year=? AND status='sent'", (kind, tbl, rid, year)).fetchone() is not None
def _log(c, kind, tbl, rid, year, to, subject, status, err=None):
    c.execute("INSERT INTO email_log(ts,kind,tbl,row_id,year,to_addr,subject,status,error) VALUES(?,?,?,?,?,?,?,?,?)",
              (datetime.datetime.now().isoformat(timespec="seconds"), kind, tbl, rid, year, to, subject, status, err))
def _page(org, title, body):
    return (f'<div style="font-family:Arial,Helvetica,sans-serif;max-width:640px;margin:auto;color:#222;font-size:14px">'
            f'<div style="border-bottom:3px solid {E(org.get("color") or "#0f5e63")};padding-bottom:6px"><b style="font-size:18px;color:{E(org.get("color") or "#0f5e63")}">{E(org.get("name"))}</b><br><span style="color:#666;font-size:12px">{E(org.get("tagline"))}</span></div>'
            f'<h2 style="font-size:16px">{E(title)}</h2>{body}'
            f'<p style="color:#888;font-size:11px;margin-top:20px">{E(org.get("name"))} · {E(org.get("phone"))} · {E(org.get("email"))}</p></div>')
def _table(head, rows):
    th = "".join(f'<th style="text-align:left;border-bottom:1px solid #ccc;padding:4px 6px;font-size:12px">{E(h)}</th>' for h in head)
    tr = "".join("<tr>" + "".join(f'<td style="padding:4px 6px;border-bottom:1px solid #eee">{E(x)}</td>' for x in r) + "</tr>" for r in rows)
    return f'<table style="border-collapse:collapse;width:100%"><tr>{th}</tr>{tr}</table>'

# ======================================================================= digest
def digest(c):
    s, today, P = logic.ctx(c)
    dash = logic.dashboard(c)
    cut = (today - datetime.timedelta(days=365)).isoformat()
    d = dict(date=today.isoformat(), alerts=dash["alerts"],
             calls=logic.rows(c, "SELECT code, name, phone, next_followup FROM donors WHERE COALESCE(next_followup,'')<>'' AND next_followup<=:today ORDER BY next_followup LIMIT 15", P),
             receipts=logic.rows(c, "SELECT n.receipt_no, n.date, d.name, n.amount FROM donations n JOIN donors d ON d.id=n.donor_id WHERE n.receipt_given='N' ORDER BY n.date LIMIT 15"),
             thanks=logic.rows(c, "SELECT n.receipt_no, n.date, d.name, n.amount FROM donations n JOIN donors d ON d.id=n.donor_id WHERE n.thank_you_sent='N' ORDER BY n.date LIMIT 15"),
             lapsed=logic.rows(c, "SELECT d.name, d.phone, MAX(n.date) last_gift, SUM(n.amount) total FROM donors d JOIN donations n ON n.donor_id=d.id GROUP BY d.id HAVING MAX(n.date)<:cut ORDER BY total DESC LIMIT 10", dict(cut=cut)),
             birthdays=[b for b in logic.birthday_people(c, 7)],
             compliance=[x for x in logic.compliance_list(c) if x["cstatus"] in ("Overdue", "Due soon")],
             pledges=c.execute("SELECT COUNT(*) FROM pledges WHERE status='New'").fetchone()[0])
    d["empty"] = not (d["alerts"] or d["calls"] or d["receipts"] or d["thanks"] or d["lapsed"] or d["birthdays"] or d["compliance"] or d["pledges"])
    return d

def digest_text(d, org):
    L = [f"{org.get('name')} · morning digest · {d['date']}", ""]
    def sec(title, lines):
        if lines: L.extend([title.upper(), *["  - " + x for x in lines], ""])
    sec("Needs attention", [a["text"] for a in d["alerts"]])
    sec("Donors to call", [f"{x['name']} {x['phone'] or ''} (due {x['next_followup']})" for x in d["calls"]])
    sec("Birthdays (next 7 days)", [f"{b['name']} - " + ("today" if b["days_away"] == 0 else f"in {b['days_away']} days") for b in d["birthdays"]])
    sec("Receipts to give", [f"{x['receipt_no']} {x['name']} {money(x['amount'])}" for x in d["receipts"]])
    sec("Thank-yous to send", [f"{x['receipt_no']} {x['name']}" for x in d["thanks"]])
    sec("Donors who have not given for a year", [f"{x['name']} (last gift {x['last_gift']}, total {money(x['total'])})" for x in d["lapsed"]])
    sec("Compliance dates", [f"{x['title']} - {x['cstatus']} ({x['next_due']})" for x in d["compliance"]])
    if d["pledges"]: sec("Pledges", [f"{d['pledges']} new pledge(s) from the Donate page to check"])
    return "\n".join(L)

def digest_html(d, org):
    b = ""
    def sec(title, head, rows):
        nonlocal b
        if rows: b += f'<h3 style="font-size:14px;margin:16px 0 4px">{E(title)}</h3>' + _table(head, rows)
    sec("Needs attention", ["What"], [[a["text"]] for a in d["alerts"]])
    sec("Donors to call", ["Donor", "Phone", "Due"], [[x["name"], x["phone"], x["next_followup"]] for x in d["calls"]])
    sec("Birthdays, next 7 days", ["Who", "When"], [[x["name"], "Today" if x["days_away"] == 0 else f"in {x['days_away']} days"] for x in d["birthdays"]])
    sec("Receipts to give", ["Receipt", "Donor", "Amount"], [[x["receipt_no"], x["name"], money(x["amount"])] for x in d["receipts"]])
    sec("Thank-yous to send", ["Receipt", "Donor"], [[x["receipt_no"], x["name"]] for x in d["thanks"]])
    sec("Donors who have not given for a year", ["Donor", "Last gift", "Total given"], [[x["name"], x["last_gift"], money(x["total"])] for x in d["lapsed"]])
    sec("Compliance dates", ["What", "Status", "Due"], [[x["title"], x["cstatus"], x["next_due"]] for x in d["compliance"]])
    if d["pledges"]: b += f'<p><b>{d["pledges"]}</b> new pledge(s) from the Donate page to check.</p>'
    return _page(org, "Morning digest · " + d["date"], b)

def _send_each(c, s, to_list, subject, text, html, kind, tbl, rid_of, year):
    """Send to each recipient once per (kind, year); returns (sent, failed, errors)."""
    sent = failed = 0; errs = []
    for to in to_list:
        rid = rid_of(to)
        if _already(c, kind, tbl, rid, year): continue
        try:
            mailer.send_mail(s, to, subject, text, html); _log(c, kind, tbl, rid, year, to, subject, "sent"); sent += 1
        except MailError as e:
            _log(c, kind, tbl, rid, year, to, subject, "failed", str(e)); failed += 1; errs.append(str(e))
        if SEND_DELAY: time.sleep(SEND_DELAY)
    c.commit()
    return sent, failed, errs

def send_digest(c, force=False):
    s, today, P = logic.ctx(c)
    to = recipients(s, "digest_to")
    if not to: return dict(sent=0, note="No recipients. Add emails in Settings → Automation.")
    d = digest(c)
    if d["empty"]: return dict(sent=0, note="Nothing to report today.")
    org = logic.org_info(s); year = int(today.strftime("%Y%m%d"))
    if force: year += 0
    sent, failed, errs = _send_each(c, s, to, f"{org.get('name')}: morning digest {d['date']}", digest_text(d, org), digest_html(d, org), "digest", "digest", _rid, year)
    return dict(sent=sent, failed=failed, errors=errs)

# ======================================================================= deadline alerts (grant reports + compliance)
def _bands(s):
    out = []
    for x in re.split(r"[,;\s]+", s.get("grant_alert_days", "") or ""):
        if x.isdigit(): out.append(int(x))
    return sorted(set(out)) or [30, 15, 7]

def deadline_triggers(c):
    s, today, P = logic.ctx(c); bands = _bands(s); out = []
    for g in logic.grants_list(c):
        if not g.get("report_due"): continue
        days = g["report_in_days"]
        if days is None: continue
        ykey = int(g["report_due"].replace("-", ""))
        band = 0 if days < 0 else next((b for b in bands if days <= b), None)
        if band is None: continue
        txt = f"Report for grant {g['code']} ({g['funder']}) is {-days} days overdue" if days < 0 else f"Report for grant {g['code']} ({g['funder']}) is due in {days} days ({g['report_due']})"
        out.append(dict(tbl=f"grant_alert:{band}", rid=g["id"], year=ykey, text=txt, level="red" if days < 0 else "amber"))
    for x in logic.compliance_list(c):
        if x["cstatus"] in ("Overdue", "Due soon"):
            band = "overdue" if x["cstatus"] == "Overdue" else "due"
            txt = f"{x['title']}: " + (f"{-x['days_left']} days overdue" if x["days_left"] < 0 else f"due in {x['days_left']} days ({x['next_due']})")
            out.append(dict(tbl=f"compliance:{band}", rid=x["id"], year=int(x["next_due"].replace("-", "")), text=txt, level="red" if band == "overdue" else "amber"))
    return out

def send_deadline_alerts(c):
    s, today, P = logic.ctx(c)
    to = recipients(s, "digest_to")
    if not to: return dict(sent=0, note="No recipients. Add emails in Settings → Automation.")
    new = [t for t in deadline_triggers(c) if not _already(c, "deadline", t["tbl"], t["rid"], t["year"])]
    if not new: return dict(sent=0, note="No new deadlines")
    org = logic.org_info(s)
    text = f"{org.get('name')}: deadlines that need action\n\n" + "\n".join("  - " + t["text"] for t in new)
    html = _page(org, "Deadlines that need action", _table(["What"], [[t["text"]] for t in new]))
    subject = f"{org.get('name')}: {len(new)} deadline alert(s)"
    ok = 0; errs = []
    for addr in to:
        try: mailer.send_mail(s, addr, subject, text, html); ok += 1
        except MailError as e: errs.append(str(e))
        if SEND_DELAY: time.sleep(SEND_DELAY)
    for t in new:
        _log(c, "deadline", t["tbl"], t["rid"], t["year"], ", ".join(to), subject, "sent" if ok else "failed", None if ok else "; ".join(errs)[:300])
    c.commit()
    return dict(sent=ok, alerts=len(new), errors=errs)

# ======================================================================= receipt + thank-you email
def receipt_email(c, donation_id, force=False):
    s, today, P = logic.ctx(c)
    r = logic.one(c, logic.TABLE_SQL["donations"] + " WHERE t.id=:i", dict(i=donation_id))
    if not r: raise MailError("Donation not found")
    donor = logic.one(c, "SELECT * FROM donors WHERE id=:i", dict(i=r["donor_id"]))
    if not EMAIL_RE.match(donor.get("email") or ""): raise MailError("This donor has no email address")
    if not force and _already(c, "receipt", "donations", donation_id, 0): return dict(status="skipped", reason="Already emailed")
    org = logic.org_info(s); words = logic.amount_words(r["amount"])
    msg = mailer.render(s.get("thanks_message", ""), dict(name=donor["name"], amount=f"{r['amount']:,.0f}", receipt=r["receipt_no"], org=org.get("name", ""), contact=" · ".join(x for x in (org.get("phone"), org.get("email")) if x)))
    text = (f"{org.get('name')}\n{org.get('address','')}\n{org.get('reg','')}\n\nDONATION RECEIPT\nReceipt no: {r['receipt_no']}\nDate: {r['date']}\nReceived from: {donor['name']}\n"
            f"Amount: {money(r['amount'])} ({words})\nPurpose: {r['purpose'] or 'General'}\nMode: {r['mode'] or ''}  Reference: {r['reference'] or ''}\n\n{msg}\n")
    body = _table(["Receipt no", "Date", "Amount", "Purpose", "Mode"], [[r["receipt_no"], r["date"], money(r["amount"]), r["purpose"] or "General", r["mode"] or ""]])
    html = _page(org, "Donation receipt", f'<p>Received from <b>{E(donor["name"])}</b></p>{body}<p>{E(words)}</p><p>{E(msg)}</p><p style="font-size:11px;color:#777">{E(org.get("reg"))}</p>')
    subject = f"Receipt {r['receipt_no']} from {org.get('name')}"
    try:
        mailer.send_mail(s, donor["email"], subject, text, html)
    except MailError as e:
        _log(c, "receipt", "donations", donation_id, 0, donor["email"], subject, "failed", str(e)); c.commit(); raise
    _log(c, "receipt", "donations", donation_id, 0, donor["email"], subject, "sent")
    c.execute("UPDATE donations SET receipt_given='Y', thank_you_sent='Y' WHERE id=?", (donation_id,)); c.commit()
    return dict(status="sent")

def auto_receipt_async(donation_id):
    """Called after a donation is saved. Sends in the background so saving stays fast."""
    def job():
        try:
            c = db.connect(); s = db.get_settings(c)
            if s.get("auto_receipt_email") == "Yes" and s.get("smtp_host"):
                try: receipt_email(c, donation_id)
                except MailError: pass
            c.close()
        except Exception as e: print("auto receipt:", e)
    t = threading.Thread(target=job, daemon=True); t.start(); return t

# ======================================================================= scheduled reports
def _prev_month(today):
    d = today.replace(day=1) - datetime.timedelta(days=1); return d.strftime("%Y-%m")

def send_trustee_report(c):
    s, today, P = logic.ctx(c)
    to = recipients(s, "trustee_emails")
    if not to: return dict(sent=0, note="No trustee emails set")
    if today.day < int(db.num(s, "report_day", 5)): return dict(sent=0, note="Not yet the report day")
    month = _prev_month(today); rep = logic.trustee_report(c, month); t = rep["totals"]
    org = rep["org"]
    rows = [[f["fund"], f["type"], money(f["opening"]), money(f["receipts"]), money(f["payments"]), money(f["closing"])] for f in rep["funds"]]
    rows.append(["Total", "", money(t["opening"]), money(t["receipts"]), money(t["payments"]), money(t["closing"])])
    body = f'<p>Month: <b>{E(month)}</b>. Surplus: <b>{money(t["surplus"])}</b></p>' + _table(["Fund", "Type", "Opening", "Receipts", "Payments", "Closing"], rows)
    if rep["payment_heads"]: body += "<h3>Payments by head</h3>" + _table(["Head", "Amount"], [[h["head"], money(h["amount"])] for h in rep["payment_heads"]])
    body += '<p style="font-size:11px;color:#777">Your own working books for trustees. Year-end accounts and audit are for your CA.</p>'
    text = f"{org.get('name')} trustee report {month}\nOpening {money(t['opening'])}, receipts {money(t['receipts'])}, payments {money(t['payments'])}, closing {money(t['closing'])}\n\n" + "\n".join(f"{r[0]}: closing {r[5]}" for r in rows[:-1])
    sent, failed, errs = _send_each(c, s, to, f"{org.get('name')}: trustee report {month}", text, _page(org, f"Trustee report · {month}", body), "trustee", "report", _rid, int(month.replace("-", "")))
    return dict(sent=sent, failed=failed, errors=errs)

def impact_email(c, donor, projects_with_gift, org, s):
    parts = []; text = [f"Dear {donor['name']},", "", f"Here is how your support to {org.get('name')} is being used.", ""]
    for pid, gift in projects_with_gift:
        r = logic.impact_report(c, pid, donor["name"], gift); n = r["numbers"]
        rows = [[x["result"], f"{x['achieved']:,.0f} of {x['target']:,.0f} {x['unit'] or ''}", f"{round((x['done'] or 0) * 100)}%"] for x in n["results"][:6]]
        sec = f'<h3 style="margin:18px 0 4px">{E(r["project"]["name"])}</h3><p style="color:#666;margin:0">{E(r["project"]["place"])}</p>'
        sec += _table(["Result", "Achieved", "Done"], rows) if rows else ""
        sec += f'<p>People reached: <b>{n["people"]:,.0f}</b> · Money used {money(n["used"])} of {money(n["budget"])}</p>'
        if r["per100"]:
            sec += _table(["Where it went", "Of every ₹100", "Of your gift"], [[x["head"], f"₹{x['share']:.0f}", money(r["split"][i]["amount"]) if r["split"] else ""] for i, x in enumerate(r["per100"])])
        if r["story"] and r["story"].get("person"):
            st = r["story"]; sec += f'<p style="margin-top:10px"><b>{E(st["person"])}:</b> {E(st.get("after") or "")}</p>'
        parts.append(sec)
        text += [r["project"]["name"], f"  People reached {n['people']:,.0f}; money used {money(n['used'])} of {money(n['budget'])}"] + [f"  {x['result']}: {x['achieved']:,.0f}/{x['target']:,.0f}" for x in n["results"][:6]] + [""]
    text.append("With thanks,\n" + org.get("name", ""))
    return "\n".join(text), _page(org, "Your impact report", f"<p>Dear {E(donor['name'])},</p><p>Here is how your support is being used.</p>" + "".join(parts) + f"<p>With thanks,<br>{E(org.get('name'))}</p>")

def send_impact_reports(c):
    s, today, P = logic.ctx(c)
    if today.month not in (1, 4, 7, 10): return dict(sent=0, note="Not a quarter-start month")
    if today.day < int(db.num(s, "report_day", 5)): return dict(sent=0, note="Not yet the report day")
    year = today.year * 10 + (today.month - 1) // 3 + 1; org = logic.org_info(s)
    projects = {p["name"].lower(): p["id"] for p in logic.rows(c, "SELECT id, name FROM projects")}
    sent = failed = 0
    for d in logic.rows(c, "SELECT * FROM donors WHERE COALESCE(email,'')<>'' AND COALESCE(wishes,'Y')<>'N'"):
        if not EMAIL_RE.match(d["email"]) or _already(c, "impact", "donors", d["id"], year): continue
        gifts = {}
        for g in logic.rows(c, "SELECT purpose, SUM(amount) a FROM donations WHERE donor_id=:i GROUP BY purpose", dict(i=d["id"])):
            pid = projects.get((g["purpose"] or "").lower())
            if pid and logic.rows(c, "SELECT 1 FROM results WHERE project_id=:p LIMIT 1", dict(p=pid)): gifts[pid] = g["a"]
        if not gifts: continue
        text, html = impact_email(c, d, list(gifts.items()), org, s); subject = f"{org.get('name')}: what your gift has done"
        try:
            mailer.send_mail(s, d["email"], subject, text, html); _log(c, "impact", "donors", d["id"], year, d["email"], subject, "sent"); sent += 1
        except MailError as e:
            _log(c, "impact", "donors", d["id"], year, d["email"], subject, "failed", str(e)); failed += 1
        c.commit()
        if SEND_DELAY: time.sleep(SEND_DELAY)
    return dict(sent=sent, failed=failed)

# ======================================================================= backup
def backup_dir(): return os.path.join(os.path.dirname(os.path.abspath(db.DB_PATH)), "backups")

def _enc_on(s): return s.get("backup_encrypt") == "Yes" and bool(s.get("backup_password"))
def _backup_name(s): return f"ngo-{datetime.date.today().isoformat()}." + ("ngobk" if _enc_on(s) else "db")

def run_backup(c):
    from . import securebackup
    s = db.get_settings(c); os.makedirs(backup_dir(), exist_ok=True)
    if s.get("backup_encrypt") == "Yes" and not s.get("backup_password"):
        return dict(ok=False, note="Password-protected backups are switched on but no backup password is set (Settings → Automation).")
    name = _backup_name(s); dst_path = os.path.join(backup_dir(), name)
    if _enc_on(s):
        try: blob = securebackup.make(c, s["backup_password"])
        except securebackup.BackupError as e: return dict(ok=False, note=e.msg)
        with open(dst_path, "wb") as fh: fh.write(blob)
    else:
        dst = sqlite3.connect(dst_path); c.backup(dst); dst.close()
    keep = max(1, int(db.num(s, "backup_keep", 30)))
    files = sorted(f for f in os.listdir(backup_dir()) if re.fullmatch(r"ngo-\d{4}-\d{2}-\d{2}\.(db|ngobk)", f))
    for old in files[:-keep]: os.remove(os.path.join(backup_dir(), old))
    note = "saved " + name + (" (password-protected)" if _enc_on(s) else "")
    cp = (s.get("backup_copy_dir") or "").strip()
    if cp:
        try:
            os.makedirs(cp, exist_ok=True); shutil.copy2(dst_path, os.path.join(cp, name)); note += f"; copied to {cp}"
        except OSError as e:
            note += f"; COPY FAILED: {e}"
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M") + " · " + note
    c.execute("INSERT OR REPLACE INTO settings VALUES('last_backup',?)", (stamp,)); c.commit()
    return dict(ok="FAILED" not in note, note=stamp)

def ensure_daily_backup(c):
    s = db.get_settings(c)
    if not os.path.exists(os.path.join(backup_dir(), _backup_name(s))): return run_backup(c)

def list_backups():
    d = backup_dir()
    if not os.path.isdir(d): return []
    out = []
    for f in sorted(os.listdir(d), reverse=True):
        if re.fullmatch(r"(ngo-\d{4}-\d{2}-\d{2}\.(db|ngobk)|before-restore-[\d-]+\.db)", f):
            out.append(dict(name=f, size=os.path.getsize(os.path.join(d, f)), protected=f.endswith(".ngobk")))
    return out[:60]

# ======================================================================= bank statement import
_H_DATE = ("date", "txn date", "transaction date", "value date", "tran date", "posting date")
_H_DESC = ("narration", "description", "particulars", "remarks", "details", "transaction remarks", "transaction details")
_H_REF = ("ref no", "ref", "reference", "chq/ref no", "cheque no", "chq no", "utr", "ref no./cheque no.", "chq./ref.no.", "transaction id", "txn id")
_H_DR = ("debit", "withdrawal", "withdrawals", "withdrawal amt.", "dr", "debit amount", "withdrawal amount")
_H_CR = ("credit", "deposit", "deposits", "deposit amt.", "cr", "credit amount", "deposit amount")
_H_AMT = ("amount", "txn amount", "transaction amount")
_H_TYPE = ("dr/cr", "type", "cr/dr", "transaction type")

def _num(x):
    x = (x or "").strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
    if not x: return None
    sign = -1 if x.startswith("-") or (x.startswith("(") and x.endswith(")")) else 1
    suffix = re.search(r"(cr|dr)\.?$", x, re.I)
    if suffix: x = x[:suffix.start()]; sign = -1 if suffix.group(1).lower() == "dr" else sign
    x = x.strip("-() ")
    try: return sign * float(x)
    except ValueError: return None

def _date(x):
    x = (x or "").strip()
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d.%m.%Y", "%Y/%m/%d"):
        try: return datetime.datetime.strptime(x, f).date().isoformat()
        except ValueError: pass
    return None

def parse_bank_csv(text):
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    hi = None
    for i, r in enumerate(rows[:60]):
        low = [x.strip().lower() for x in r]
        if sum(1 for x in low if x) >= 3 and any(x in _H_DATE for x in low) and any(x in _H_DR + _H_CR + _H_AMT for x in low): hi = i; break
    if hi is None: raise ValueError("Could not find the header row. The file needs columns like Date, Narration, Debit, Credit (or Amount).")
    head = [x.strip().lower() for x in rows[hi]]
    idx = lambda names: next((i for i, x in enumerate(head) if x in names), None)
    cd, cn, cr_, cdr, ccr, cam, cty = idx(_H_DATE), idx(_H_DESC), idx(_H_REF), idx(_H_DR), idx(_H_CR), idx(_H_AMT), idx(_H_TYPE)
    out, seen = [], {}
    for r in rows[hi + 1:]:
        if cd is None or cd >= len(r): continue
        d = _date(r[cd])
        if not d: continue
        g = lambda i: r[i].strip() if i is not None and i < len(r) else ""
        amt = typ = None
        dr, cr = _num(g(cdr)), _num(g(ccr))
        if cr and cr > 0: amt, typ = abs(cr), "Receipt"
        elif dr and abs(dr) > 0: amt, typ = abs(dr), "Payment"
        elif cam is not None:
            a = _num(g(cam)); t = g(cty).lower()
            if a: amt = abs(a); typ = "Payment" if (t.startswith("d") or a < 0) else "Receipt"
        if not amt: continue
        row = dict(date=d, amount=round(amt, 2), type=typ, narration=g(cn)[:200], ref=g(cr_)[:60])
        key = f"{row['date']}|{row['amount']:.2f}|{row['type']}|{row['ref']}|{row['narration']}"
        seen[key] = seen.get(key, 0) + 1
        row["hash"] = hashlib.sha1(f"{key}#{seen[key]}".encode()).hexdigest()
        out.append(row)
    if not out: raise ValueError("No transactions found under the header row.")
    return out

def _within(d1, d2, days): return abs((datetime.date.fromisoformat(d1) - datetime.date.fromisoformat(d2)).days) <= days

def bank_preview(c, text):
    rows = parse_bank_csv(text)
    taken_d = {r[0] for r in c.execute("SELECT donation_id FROM bank_txns WHERE donation_id IS NOT NULL")}
    taken_c = {r[0] for r in c.execute("SELECT cash_id FROM bank_txns WHERE cash_id IS NOT NULL")}
    known = {r[0] for r in c.execute("SELECT hash FROM bank_txns")}
    used_d, used_c = set(), set()
    dons = logic.rows(c, "SELECT n.id, n.date, n.amount, n.reference, n.fund_id, n.fund_type, d.name donor FROM donations n JOIN donors d ON d.id=n.donor_id")
    pays = logic.rows(c, "SELECT id, date, amount, party, voucher_no FROM cash_book WHERE type='Payment'")
    for r in rows:
        r["duplicate"] = r["hash"] in known; r["match"] = None; r["action"] = "skip" if r["duplicate"] else "new"
        if r["duplicate"]: continue
        nar = (r["narration"] + " " + r["ref"]).lower()
        if r["type"] == "Receipt":
            best = None
            for d in dons:
                if d["id"] in taken_d or d["id"] in used_d or abs(d["amount"] - r["amount"]) > 0.005 or not _within(d["date"], r["date"], 5): continue
                sc = 0
                ref = (d["reference"] or "").lower().strip()
                if len(ref) >= 4 and ref in nar: sc += 3
                if any(len(t) >= 3 and t in nar for t in re.split(r"\W+", d["donor"].lower())): sc += 2
                if d["date"] == r["date"]: sc += 1
                if best is None or sc > best[0]: best = (sc, d)
            if best:
                sc, d = best; used_d.add(d["id"])
                r["match"] = dict(kind="donation", id=d["id"], label=f"{d['donor']} · {d['amount']:,.0f} · {d['date']}", confidence="high" if sc >= 3 else "maybe", posted=bool(d["fund_id"]), fund_type=d["fund_type"])
                r["action"] = "match"
        else:
            best = None
            for p in pays:
                if p["id"] in taken_c or p["id"] in used_c or abs(p["amount"] - r["amount"]) > 0.005 or not _within(p["date"], r["date"], 3): continue
                sc = (2 if len(p["voucher_no"] or "") >= 3 and p["voucher_no"].lower() in nar else 0) + (2 if p["party"] and any(len(t) >= 3 and t in nar for t in re.split(r"\W+", p["party"].lower())) else 0) + (1 if p["date"] == r["date"] else 0)
                if best is None or sc > best[0]: best = (sc, p)
            if best:
                sc, p = best; used_c.add(p["id"])
                r["match"] = dict(kind="cash", id=p["id"], label=f"{p['party'] or ''} · {p['amount']:,.0f} · {p['date']}", confidence="high" if sc >= 3 else "maybe", posted=True)
                r["action"] = "match"
    return dict(rows=rows, summary=dict(total=len(rows), duplicates=sum(1 for r in rows if r["duplicate"]), matched=sum(1 for r in rows if r["action"] == "match"), new=sum(1 for r in rows if r["action"] == "new")))

def bank_commit(c, items, fund_id, user, create, update):
    """items: [{hash,date,amount,type,narration,ref,action,match_kind,match_id,head}]. Runs in the caller's transaction."""
    res = dict(matched=0, created=0, skipped=0, errors=[])
    for it in items:
        h = str(it.get("hash") or "")
        if not re.fullmatch(r"[0-9a-f]{40}", h): res["errors"].append("bad row"); continue
        if it.get("action") == "skip" or c.execute("SELECT 1 FROM bank_txns WHERE hash=?", (h,)).fetchone(): res["skipped"] += 1; continue
        base = (h, it.get("date"), float(it.get("amount") or 0), it.get("type"), (it.get("narration") or "")[:200], (it.get("ref") or "")[:60], datetime.datetime.now().isoformat(timespec="seconds"))
        if it.get("action") == "match":
            kind, mid = it.get("match_kind"), int(it.get("match_id") or 0)
            if kind == "donation":
                d = c.execute("SELECT * FROM donations WHERE id=?", (mid,)).fetchone()
                if not d: res["errors"].append(f"{it.get('narration','')[:30]}: donation not found"); continue
                if not d["fund_id"]:
                    if not fund_id: res["errors"].append(f"{d['receipt_no']}: choose a fund to post it to"); continue
                    update(c, "donations", mid, dict(fund_id=fund_id), user)
                c.execute("INSERT INTO bank_txns(hash,date,amount,type,narration,ref,imported,donation_id) VALUES(?,?,?,?,?,?,?,?)", (*base, mid))
            else:
                if not c.execute("SELECT 1 FROM cash_book WHERE id=?", (mid,)).fetchone(): res["errors"].append("payment not found"); continue
                c.execute("INSERT INTO bank_txns(hash,date,amount,type,narration,ref,imported,cash_id) VALUES(?,?,?,?,?,?,?,?)", (*base, mid))
            res["matched"] += 1
        else:
            if not fund_id: res["errors"].append("Choose a fund for new entries"); continue
            rid = create(c, "cash_book", dict(date=it["date"], type=it["type"], fund_id=fund_id, head=it.get("head") or ("Other In" if it["type"] == "Receipt" else "Other"),
                                              party=(it.get("narration") or "")[:80], mode="Bank", amount=it["amount"], note=f"Bank import {it.get('ref') or ''}".strip()), user)
            c.execute("INSERT INTO bank_txns(hash,date,amount,type,narration,ref,imported,cash_id) VALUES(?,?,?,?,?,?,?,?)", (*base, rid)); res["created"] += 1
    return res

# ======================================================================= payroll slips + bank sheet
def payslip(c, team_id, month):
    s, today, P = logic.ctx(c)
    pr = logic.payroll(c, month); row = next((r for r in pr["rows"] if r["id"] == team_id), None)
    if not row: return None
    att = logic.rows(c, "SELECT attendance, COUNT(*) n, SUM(extra_hours) h FROM attendance WHERE team_id=:t AND substr(date,1,7)=:m GROUP BY attendance", dict(t=team_id, m=month))
    extra_h = sum(a["h"] or 0 for a in att if a["attendance"] == "P"); hr = P["extra_hour_rate"]
    t = logic.one(c, "SELECT * FROM team WHERE id=:i", dict(i=team_id))
    return dict(kind="payslip", org=logic.org_info(s), month=month, member=dict(code=row["code"], name=row["name"], role=row["role"], pay_type=row["pay_type"], pay_rate=row["pay_rate"], bank_account=t.get("bank_account"), ifsc=t.get("ifsc")),
                counts={a["attendance"]: a["n"] for a in att}, days_present=row["days_present"], extra_hours=extra_h, extra_hour_rate=hr, salary=row["salary"],
                daily_pay=row["daily_pay"], travel_paid=row["travel_paid"], due=row["due"], advances=row["advances"], net=row["net"], words=logic.amount_words(max(0, row["net"])))

def bank_sheet(c, month):
    s = db.get_settings(c); pr = logic.payroll(c, month)
    acc = {r["id"]: r for r in logic.rows(c, "SELECT id, bank_account, ifsc FROM team")}
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["Team ID", "Name", "Account no", "IFSC", "Amount", "Narration"])
    for r in pr["rows"]:
        if r["net"] > 0: w.writerow([r["code"], r["name"], acc[r["id"]]["bank_account"] or "", acc[r["id"]]["ifsc"] or "", int(r["net"]), f"Salary {month}"])
    return buf.getvalue()

# ======================================================================= public pledges + duplicates
_pledge_hits = {}
def _digits(x): return re.sub(r"\D", "", x or "")[-10:]

def public_info(c):
    s = db.get_settings(c)
    on = s.get("donate_page") == "Yes" and bool(s.get("org_upi"))
    upi = s.get("org_upi", "")
    from urllib.parse import quote
    link = f"upi://pay?pa={quote(upi, safe='@')}&pn={quote(s.get('org_name', ''))}&cu=INR" if upi else ""
    return dict(enabled=on, name=s.get("org_name", ""), tagline=s.get("org_tagline", ""), upi=upi, message=s.get("donate_message", ""), link=link,
                phone=s.get("org_phone", ""), email=s.get("org_email", ""), reg=s.get("org_reg", ""), transparency=(s.get("public_transparency") == "Yes"))

def public_pledge(c, data, ip):
    s = db.get_settings(c)
    if s.get("donate_page") != "Yes": raise ValueError("The donate page is switched off")
    now = time.time(); hits = [t for t in _pledge_hits.get(ip, []) if now - t < 3600]
    if len(hits) >= 5: raise PermissionError("Too many submissions. Please try again later.")
    if (data.get("website") or "").strip(): return dict(ok=True)       # honeypot: bots fill this; pretend success
    name = (data.get("name") or "").strip(); email = (data.get("email") or "").strip(); phone = (data.get("phone") or "").strip()
    if not 2 <= len(name) <= 80: raise ValueError("Please enter your name")
    if not email and not phone: raise ValueError("Please give a phone number or an email so we can reach you")
    if email and not EMAIL_RE.match(email): raise ValueError("That email does not look right")
    if phone and not re.fullmatch(r"[0-9 +\-()]{7,20}", phone): raise ValueError("That phone number does not look right")
    try: amt = float(data.get("amount") or 0)
    except ValueError: raise ValueError("Amount must be a number")
    if amt < 0 or amt > 10_000_000: raise ValueError("Amount looks wrong")
    if c.execute("SELECT COUNT(*) FROM pledges WHERE ts>?", ((datetime.datetime.now() - datetime.timedelta(days=1)).isoformat(),)).fetchone()[0] >= 200: raise PermissionError("Too many pledges today")
    hits.append(now); _pledge_hits[ip] = hits
    c.execute("INSERT INTO pledges(ts,name,phone,email,amount,message,status,ip) VALUES(?,?,?,?,?,?,'New',?)",
              (datetime.datetime.now().isoformat(timespec="seconds"), name, phone, email, amt, (data.get("message") or "").strip()[:500], ip))
    return dict(ok=True)

def convert_pledge(c, pid, user, create):
    p = c.execute("SELECT * FROM pledges WHERE id=?", (pid,)).fetchone()
    if not p: raise ValueError("Pledge not found")
    dup = None
    if p["email"]: dup = c.execute("SELECT id FROM donors WHERE lower(email)=lower(?)", (p["email"],)).fetchone()
    if not dup and _digits(p["phone"]):
        for d in c.execute("SELECT id, phone FROM donors WHERE COALESCE(phone,'')<>''"):
            if _digits(d["phone"]) == _digits(p["phone"]): dup = d; break
    did = dup["id"] if dup else create(c, "donors", dict(name=p["name"], phone=p["phone"], email=p["email"], wishes="Y", notes="From Donate page: " + (p["message"] or "")), user)
    c.execute("UPDATE pledges SET status='Converted' WHERE id=?", (pid,))
    return dict(donor_id=did, existing=bool(dup))

def find_duplicates(c, phone="", name="", village=""):
    out = []
    ph = _digits(phone)
    for tbl, label in (("beneficiaries", "Person served"), ("donors", "Donor")):
        for r in c.execute(f"SELECT id, name, phone{', village' if tbl == 'beneficiaries' else ''} FROM {tbl}"):
            same_phone = ph and len(ph) >= 7 and _digits(r["phone"]) == ph
            same_name = tbl == "beneficiaries" and name and village and r["name"].strip().lower() == name.strip().lower() and (r["village"] or "").strip().lower() == village.strip().lower()
            if same_phone or same_name:
                out.append(dict(kind=label, id=r["id"], name=r["name"], phone=r["phone"], reason="same phone number" if same_phone else "same name and village"))
    return out

# ======================================================================= regular-giving promise reminders
def send_commitment_reminders(c):
    from . import donorcare
    s, today, _ = logic.ctx(c); org = logic.org_info(s); days = int(db.num(s, "commit_remind_days", 3)); sent = failed = 0
    for cm in donorcare.reminders_due(c, days):
        key = int(cm["next_due"].replace("-", ""))
        if _already(c, "pledge_due", "commitments", cm["id"], key): continue
        text = donorcare.draft(c, "pledge_due", cm, dict(amount=f"{cm['amount']:,.0f}", due=cm["next_due"]))
        subject = f"{org.get('name')}: a gentle reminder"
        try:
            mailer.send_mail(s, cm["email"], subject, text, _page(org, "A gentle reminder", f"<p>{E(text)}</p>")); _log(c, "pledge_due", "commitments", cm["id"], key, cm["email"], subject, "sent"); sent += 1
        except MailError as e:
            _log(c, "pledge_due", "commitments", cm["id"], key, cm["email"], subject, "failed", str(e)); failed += 1
        if SEND_DELAY: time.sleep(SEND_DELAY)
    c.commit()
    return dict(sent=sent, failed=failed)

# ======================================================================= scheduler
def tick(c):
    from . import comms
    comms.run_due(c)
    s = db.get_settings(c); hour = datetime.datetime.now().hour; did = {}
    if s.get("backup_auto", "Yes") == "Yes":
        r = ensure_daily_backup(c)
        if r: did["backup"] = r
    if s.get("smtp_host"):
        if s.get("birthday_auto") == "Yes" and hour >= int(db.num(s, "birthday_send_hour", 9)): did["birthdays"] = mailer.run_today(c)
        if hour >= int(db.num(s, "digest_hour", 8)):
            if s.get("digest_auto") == "Yes": did["digest"] = send_digest(c)
            if s.get("deadline_alerts_auto") == "Yes": did["deadlines"] = send_deadline_alerts(c)
        if s.get("trustee_report_auto") == "Yes": did["trustee"] = send_trustee_report(c)
        if s.get("impact_auto") == "Yes": did["impact"] = send_impact_reports(c)
        if s.get("commit_remind_auto") == "Yes": did["promises"] = send_commitment_reminders(c)
    if s.get("weekly_auto") == "Yes" and hour >= int(db.num(s, "digest_hour", 8)):
        from . import weekly
        r = weekly.send(c)
        if r.get("sent") or r.get("failed"): did["weekly"] = r
    return did

def scheduler(every=600):
    from . import comms
    n = 0
    while True:
        try:
            c = db.connect()
            if n % max(1, every // 60) == 0: tick(c)       # full daily jobs every 10 minutes
            else: comms.run_due(c)                          # scheduled broadcasts are checked every minute
            c.close()
        except Exception as e:
            print("scheduler:", e)
        n += 1; time.sleep(60)

def start_scheduler():
    t = threading.Thread(target=scheduler, daemon=True, name="ngo-scheduler"); t.start(); return t
