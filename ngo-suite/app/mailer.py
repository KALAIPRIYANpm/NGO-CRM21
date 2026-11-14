"""Email sending (standard library smtplib) and birthday wishes. Nothing is sent unless SMTP is set up in Settings."""
import smtplib, ssl, re, datetime, threading, time
from email.message import EmailMessage
from email.utils import formataddr
from . import db, logic

EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")

class MailError(Exception):
    pass

def render(tpl, vals):
    for k, v in vals.items():
        tpl = tpl.replace("{" + k + "}", v)
    return tpl

def _smtp_send(s, msg):
    host, port = s.get("smtp_host", "").strip(), int(db.num(s, "smtp_port", 587))
    mode = s.get("smtp_security", "starttls")
    ctx = ssl.create_default_context()
    try:
        if mode == "ssl":
            srv = smtplib.SMTP_SSL(host, port, timeout=20, context=ctx)
        else:
            srv = smtplib.SMTP(host, port, timeout=20)
            if mode == "starttls":
                srv.starttls(context=ctx)
        with srv:
            if s.get("smtp_user"):
                srv.login(s["smtp_user"], s.get("smtp_password", ""))
            srv.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"Could not send: {e}")

def send_mail(s, to, subject, body, html=None):
    if not s.get("smtp_host", "").strip():
        raise MailError("Email is not set up yet. Open Settings → Email and fill in your mail server.")
    if not EMAIL_RE.match(to or ""):
        raise MailError("That email address does not look right")
    sender = (s.get("smtp_from") or s.get("smtp_user") or "").strip()
    if not EMAIL_RE.match(sender):
        raise MailError("Set a valid 'From' email address in Settings → Email")
    msg = EmailMessage()
    msg["From"] = formataddr((re.sub(r"[\r\n]", " ", s.get("org_name", "")), sender))
    msg["To"] = to
    if EMAIL_RE.match(s.get("org_email", "") or ""):
        msg["Reply-To"] = s["org_email"]
    msg["Subject"] = re.sub(r"[\r\n]+", " ", subject).strip()[:200]
    msg.set_content(body)
    if html: msg.add_alternative(html, subtype="html")
    _smtp_send(s, msg)

def _log(c, kind, p, year, to, subject, status, err=None):
    c.execute("INSERT INTO email_log(ts,kind,tbl,row_id,year,to_addr,subject,status,error) VALUES(?,?,?,?,?,?,?,?,?)",
              (datetime.datetime.now().isoformat(timespec="seconds"), kind, p["tbl"], p["id"], year, to, subject, status, err))

def send_wish(c, p):
    """Send one birthday email. Returns {'status': 'sent'|'skipped'|'failed', 'reason': ...}. Never sends twice in the same year."""
    s = db.get_settings(c)
    year = int(p["next_date"][:4])
    if p.get("wishes") == "N":
        return dict(status="skipped", reason="Opted out of wishes")
    if not EMAIL_RE.match(p.get("email") or ""):
        return dict(status="skipped", reason="No valid email address")
    if c.execute("SELECT 1 FROM email_log WHERE kind='birthday' AND tbl=? AND row_id=? AND year=? AND status='sent'", (p["tbl"], p["id"], year)).fetchone():
        return dict(status="skipped", reason="Already sent this year")
    contact = " · ".join(x for x in (s.get("org_phone"), s.get("org_email")) if x)
    vals = dict(name=p["name"], org=s.get("org_name", ""), contact=contact, age=str(p["turning"] or ""))
    subject, body = render(s.get("birthday_subject", ""), vals), render(s.get("birthday_body", ""), vals)
    try:
        send_mail(s, p["email"], subject, body)
    except MailError as e:
        _log(c, "birthday", p, year, p["email"], subject, "failed", str(e))
        return dict(status="failed", reason=str(e))
    _log(c, "birthday", p, year, p["email"], subject, "sent")
    return dict(status="sent", reason="")

def run_today(c, respect_failures=True):
    """Send wishes to everyone whose birthday is today. A person is retried at most 3 times a day after failures."""
    sent = skipped = failed = 0; details = []
    today = logic.asof_date(c).isoformat()
    for p in logic.birthday_people(c, 0):
        if respect_failures and c.execute("SELECT COUNT(*) FROM email_log WHERE kind='birthday' AND tbl=? AND row_id=? AND status='failed' AND substr(ts,1,10)=?",
                                          (p["tbl"], p["id"], datetime.date.today().isoformat())).fetchone()[0] >= 3:
            continue
        r = send_wish(c, p)
        if r["status"] == "sent": sent += 1
        elif r["status"] == "failed": failed += 1; details.append(f"{p['name']}: {r['reason']}")
        else:
            skipped += 1
            if r["reason"] != "Already sent this year": details.append(f"{p['name']}: {r['reason']}")
    c.commit()
    return dict(sent=sent, skipped=skipped, failed=failed, details=details)

def scheduler(stop=None, every=600):
    """Background loop: once the configured hour has passed, send today's birthday wishes (if Auto is switched on)."""
    while not (stop and stop.is_set()):
        try:
            c = db.connect()
            s = db.get_settings(c)
            if s.get("birthday_auto") == "Yes" and s.get("smtp_host") and datetime.datetime.now().hour >= int(db.num(s, "birthday_send_hour", 9)):
                run_today(c)
            c.close()
        except Exception as e:  # keep the loop alive whatever happens
            print("birthday scheduler:", e)
        time.sleep(every)

def start_scheduler():
    t = threading.Thread(target=scheduler, daemon=True, name="birthday-scheduler"); t.start(); return t
