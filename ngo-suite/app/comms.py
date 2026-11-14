"""Communication and follow-up: audiences, broadcasts (email, official WhatsApp, SMS), follow-up board, donor timeline, logo storage."""
import re, base64, datetime, threading, time, json
from urllib.parse import quote
from . import db, logic, mailer, automation, gateway
from .mailer import EMAIL_RE, MailError

MAX_RECIPIENTS = 1000
DONOR_SEGS = ("all", "recent", "lapsed", "repeat", "big", "city", "never", "language")
SEGMENTS = [("all", "All donors", False), ("recent", "Donors who gave in the last 90 days", False), ("lapsed", "Donors who gave before, but not in the last 12 months", False),
            ("repeat", "Repeat donors", False), ("big", "Donors whose total giving is at least ₹ …", True), ("city", "Donors in a city …", True), ("never", "Donors who never gave", False), ("language", "Donors who prefer a language …", True),
            ("contacts_all", "All contacts (non-donors)", False), ("contacts_group", "Contacts in a group …", True), ("everyone", "Everyone (donors and contacts)", False)]
OPT_OUT_LINE = "\n\nIf you would rather not get these messages, just reply STOP and we will remove you."
CHANNELS = ("email", "whatsapp", "sms")
CONSENT = dict(email="wishes", whatsapp="msg_optin", sms="msg_optin")

def segment_donors(c, seg, param="", channel="email"):
    s, today, P = logic.ctx(c)
    rows = logic.rows(c, """SELECT d.id, d.name, d.email, d.phone, d.city, d.language, d.wishes, d.msg_optin, COALESCE(SUM(n.amount),0) total, COUNT(n.id) gifts, MAX(n.date) last
                            FROM donors d LEFT JOIN donations n ON n.donor_id=d.id GROUP BY d.id ORDER BY d.name""")
    c12 = (today - datetime.timedelta(days=365)).isoformat(); c90 = (today - datetime.timedelta(days=90)).isoformat()
    need = int(db.num(s, "repeat_gifts", 2))
    try: amt = float(param or 0)
    except ValueError: amt = 0
    f = dict(all=lambda r: True, everyone=lambda r: True, recent=lambda r: r["last"] and r["last"] >= c90, lapsed=lambda r: r["gifts"] > 0 and r["last"] < c12,
             repeat=lambda r: r["gifts"] >= need, big=lambda r: r["total"] >= amt, city=lambda r: (r["city"] or "").strip().lower() == (param or "").strip().lower() and bool(param),
             never=lambda r: r["gifts"] == 0, language=lambda r: bool(param) and (r["language"] or "English").strip().lower() == param.strip().lower()).get(seg)
    if not f: raise ValueError("Pick who to send to")
    col = CONSENT.get(channel, "wishes")
    return [dict(r, kind="donor") for r in rows if (r[col] or "Y") != "N" and f(r)]

def segment_contacts(c, seg, param="", channel="email"):
    if seg not in ("contacts_all", "contacts_group", "everyone"): return []
    col = CONSENT.get(channel, "wishes"); out = []
    for r in logic.rows(c, "SELECT * FROM contacts ORDER BY name"):
        if (r[col] or "Y") == "N": continue
        if seg == "contacts_group" and (not param or param.strip().lower() not in [x.strip().lower() for x in (r["tags"] or "").split(",")]): continue
        out.append(dict(r, kind="contact"))
    return out

def audience(c, seg, param="", channel="email"):
    """People who can be reached on this channel and agreed to it, one per address."""
    if seg not in DONOR_SEGS + ("contacts_all", "contacts_group", "everyone"): raise ValueError("Pick who to send to")
    people = (segment_donors(c, seg, param, channel) if seg in DONOR_SEGS or seg == "everyone" else []) + segment_contacts(c, seg, param, channel)
    seen, out = set(), []
    blocked = set() if channel == "email" else {r["phone"] for r in c.execute("SELECT phone FROM optout")}      # replied STOP: never message, even if the record says OK
    for r in people:
        if channel == "email":
            e = (r.get("email") or "").strip()
            if not EMAIL_RE.match(e): continue
            key = e.lower()
        else:
            key = gateway.normalise_phone(r.get("phone"))
            if not key or key in blocked: continue
        if key in seen: continue
        seen.add(key); out.append(dict(r, to=(e if channel == "email" else key)))
    return out

def _vals(s, d):
    o = logic.org_info(s)
    first = (d["name"] or "").split()[0] if d.get("name") else ""
    return dict(name=d.get("name") or "", first_name=first, org=o.get("name", ""), upi=o.get("upi", ""), contact=" · ".join(x for x in (o.get("phone"), o.get("email")) if x))

def preview(c, seg, param):
    counts = {ch: len(audience(c, seg, param, ch)) for ch in CHANNELS}
    people = (segment_donors(c, seg, param, "email") if seg in DONOR_SEGS or seg == "everyone" else []) + segment_contacts(c, seg, param, "email")
    allp = (segment_donors(c, seg, param, "whatsapp") if seg in DONOR_SEGS or seg == "everyone" else []) + segment_contacts(c, seg, param, "whatsapp")
    sample = [r["name"] for r in (allp or people)[:6]]
    return dict(counts=counts, total=max(counts.values()), sample=sample, with_email=counts["email"], with_phone=counts["whatsapp"])

def groups(c):
    out = set()
    for r in c.execute("SELECT tags FROM contacts WHERE COALESCE(tags,'')<>''"):
        for t in r[0].split(","):
            if t.strip(): out.add(t.strip())
    return sorted(out, key=str.lower)

def _html_body(s, subject, text):
    o = logic.org_info(s)
    paras = "".join(f'<p style="margin:0 0 10px">{automation.E(p).replace(chr(10), "<br>")}</p>' for p in text.split("\n\n"))
    return automation._page(o, subject, paras)

def _check_ready(s, channel, template):
    if channel == "email":
        if not s.get("smtp_host"): raise ValueError("Set up email in Settings first")
    elif not gateway.configured(s, channel):
        raise ValueError(("WhatsApp" if channel == "whatsapp" else "SMS") + " is not connected yet. Open Settings → Official WhatsApp and SMS.")
    elif channel == "sms" and s.get("sms_provider") == "MSG91" and not template:
        raise ValueError("MSG91 needs your DLT-approved template ID")

def start_campaign(c, user, name, seg, param, subject, body, channel="email", template="", variables="", schedule_at=""):
    s = db.get_settings(c)
    if channel not in CHANNELS: raise ValueError("Pick email, WhatsApp or SMS")
    _check_ready(s, channel, (template or "").strip())
    name, subject, body = (name or "").strip(), (subject or "").strip(), (body or "").strip()
    if not name or not body or (channel == "email" and not subject): raise ValueError("Give the message a name" + (", a subject" if channel == "email" else "") + " and some text")
    if len(body) > 5000 or len(subject) > 200: raise ValueError("Message is too long")
    if channel == "sms" and len(body) > 640: raise ValueError("SMS text is too long (640 characters at most)")
    to = audience(c, seg, param, channel)
    if not to: raise ValueError("Nobody in that group can be reached on this channel (check phone numbers or email, and permission to message)")
    if len(to) > MAX_RECIPIENTS: raise ValueError(f"At most {MAX_RECIPIENTS} messages per send. Narrow the group.")
    sched = (schedule_at or "").strip()
    if sched:
        try: dt = datetime.datetime.fromisoformat(sched)
        except ValueError: raise ValueError("Send time looks wrong")
        if dt <= datetime.datetime.now() + datetime.timedelta(minutes=1): sched = ""
        elif dt > datetime.datetime.now() + datetime.timedelta(days=90): raise ValueError("Pick a time within the next 90 days")
        else: sched = dt.isoformat(timespec="minutes")
    cur = c.execute("INSERT INTO campaigns(ts,name,channel,segment,subject,body,total,status,user,schedule_at,provider_template,variables) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (datetime.datetime.now().isoformat(timespec="seconds"), name, channel, seg + (":" + param if param else ""), subject, body, len(to), "Scheduled" if sched else "Sending",
                     user["username"], sched or None, (template or "").strip(), (variables or "").strip()))
    cid = cur.lastrowid; c.commit()
    t = None
    if not sched: t = threading.Thread(target=_run, args=(cid,), daemon=True); t.start()
    return cid, len(to), t, sched

def _delay(channel): return automation.SEND_DELAY if channel == "email" else automation.SEND_DELAY * 0.3

def _run(cid, only_failed=False):
    c = db.connect()
    try:
        s = db.get_settings(c); camp = logic.one(c, "SELECT * FROM campaigns WHERE id=:i", dict(i=cid))
        if not camp: return
        ch = camp["channel"].lower(); seg, _, param = (camp["segment"] or "").partition(":")
        if only_failed:
            bad = {(r["kind"], r["rid"]): r["id"] for r in c.execute("SELECT id, kind, rid FROM messages WHERE campaign_id=? AND status='failed'", (cid,))}
            to = [d for d in audience(c, seg, param, ch) if (d["kind"], d["id"]) in bad]
            mids = bad
        else:
            to, mids = audience(c, seg, param, ch), {}
        names = [p.strip() for p in (camp["variables"] or "").split(",") if p.strip()]
        n = 0
        for d in to:
            n += 1
            if n % 10 == 0 and c.execute("SELECT status FROM campaigns WHERE id=?", (cid,)).fetchone()[0] == "Cancelled": break
            v = _vals(s, d); err = pid = None
            try:
                if ch == "email":
                    subj = mailer.render(camp["subject"], v); text = mailer.render(camp["body"], v) + OPT_OUT_LINE
                    mailer.send_mail(s, d["to"], subj, text, _html_body(s, subj, text))
                else:
                    text = mailer.render(camp["body"], v)
                    pid = gateway.send(s, ch, d["to"], text, [v.get(x, "") for x in names], camp["provider_template"] or "")
                st = "sent"
            except (MailError, gateway.GatewayError) as e:
                st, err = "failed", str(e)[:300]
            now = datetime.datetime.now().isoformat(timespec="seconds")
            if (d["kind"], d["id"]) in mids:
                c.execute("UPDATE messages SET status=?, error=?, provider_id=?, ts=? WHERE id=?", (st, err, pid, now, mids[(d["kind"], d["id"])]))
            else:
                c.execute("INSERT INTO messages(campaign_id,kind,rid,name,to_addr,channel,status,error,provider_id,ts) VALUES(?,?,?,?,?,?,?,?,?,?)", (cid, d["kind"], d["id"], d["name"], d["to"], ch, st, err, pid, now))
                if ch == "email": automation._log(c, "campaign", "donors", d["id"], cid, d["to"], camp["subject"], st, err) if d["kind"] == "donor" else None
                elif st == "sent" and d["kind"] == "donor":
                    c.execute("INSERT INTO interactions(date,donor_id,channel,direction,summary,owner) VALUES(?,?,?,?,?,?)",
                              (now[:10], d["id"], "WhatsApp" if ch == "whatsapp" else "SMS", "Out", f"Broadcast: {camp['name']}", "Broadcast"))
            c.execute("UPDATE campaigns SET sent=(SELECT COUNT(*) FROM messages WHERE campaign_id=? AND status='sent'), failed=(SELECT COUNT(*) FROM messages WHERE campaign_id=? AND status='failed') WHERE id=?", (cid, cid, cid)); c.commit()
            if _delay(ch): time.sleep(_delay(ch))
        c.execute("UPDATE campaigns SET status=CASE WHEN status='Cancelled' THEN 'Cancelled' ELSE 'Done' END WHERE id=?", (cid,)); c.commit()
    except Exception as e:  # pragma: no cover
        c.execute("UPDATE campaigns SET status='Stopped' WHERE id=?", (cid,)); c.commit(); print("campaign:", e)
    finally:
        c.close()

def run_due(c):
    now = datetime.datetime.now().isoformat(timespec="minutes"); started = []
    for r in c.execute("SELECT id FROM campaigns WHERE status='Scheduled' AND schedule_at<=?", (now,)).fetchall():
        if c.execute("UPDATE campaigns SET status='Sending' WHERE id=? AND status='Scheduled'", (r["id"],)).rowcount:
            c.commit(); t = threading.Thread(target=_run, args=(r["id"],), daemon=True); t.start(); started.append(t)
    return started

def retry_failed(c, cid):
    camp = logic.one(c, "SELECT * FROM campaigns WHERE id=:i", dict(i=cid))
    if not camp: raise ValueError("Not found")
    if camp["status"] in ("Sending", "Scheduled"): raise ValueError("This send is still running")
    _check_ready(db.get_settings(c), camp["channel"].lower(), camp["provider_template"])
    c.execute("UPDATE campaigns SET status='Sending' WHERE id=?", (cid,)); c.commit()
    t = threading.Thread(target=_run, args=(cid, True), daemon=True); t.start(); return t

def cancel(c, cid):
    n = c.execute("UPDATE campaigns SET status='Cancelled' WHERE id=? AND status IN ('Scheduled','Sending')", (cid,)).rowcount
    if not n: raise ValueError("This send has already finished")

def campaign_detail(c, cid):
    camp = logic.one(c, "SELECT id,ts,name,channel,segment,subject,body,total,sent,failed,status,user,schedule_at,provider_template,variables FROM campaigns WHERE id=:i", dict(i=cid))
    if not camp: return None
    camp["messages"] = logic.rows(c, "SELECT name, to_addr, status, error, ts FROM messages WHERE campaign_id=:i ORDER BY id LIMIT 1000", dict(i=cid))
    return camp

def whatsapp_list(c, seg, param, body):
    """Click-to-send list for people who prefer to use their own phone."""
    s = db.get_settings(c); out = []
    for d in audience(c, seg, param, "whatsapp"):
        text = mailer.render(body, _vals(s, d))
        out.append(dict(id=d["id"], kind=d["kind"], name=d["name"], phone=d["phone"], text=text, link=f"https://wa.me/{d['to']}?text={quote(text)}"))
    return out[:MAX_RECIPIENTS]

def test_gateway(c, channel, to, template, variables):
    s = db.get_settings(c)
    if channel not in ("whatsapp", "sms"): raise ValueError("Pick WhatsApp or SMS")
    names = [p.strip() for p in (variables or "").split(",") if p.strip()]
    v = _vals(s, dict(name="Test Person"))
    try:
        pid = gateway.send(s, channel, to, "Test message from " + v["org"], [v.get(x, "") for x in names], (template or "").strip())
    except gateway.GatewayError as e:
        raise ValueError(str(e))
    return dict(ok=True, provider_id=pid)

def followups(c):
    s, today, P = logic.ctx(c); t = today.isoformat(); soon = (today + datetime.timedelta(days=7)).isoformat()
    rows = logic.rows(c, """SELECT d.id, d.code, d.name, d.phone, d.email, d.next_followup,
        (SELECT MAX(date) FROM donations WHERE donor_id=d.id) last_gift, (SELECT COALESCE(SUM(amount),0) FROM donations WHERE donor_id=d.id) total
        FROM donors d WHERE COALESCE(d.next_followup,'')<>'' AND d.next_followup<=:soon ORDER BY d.next_followup, d.name""", dict(soon=soon))
    for r in rows:
        li = logic.one(c, "SELECT date, channel, outcome, summary FROM interactions WHERE donor_id=:i ORDER BY date DESC, id DESC LIMIT 1", dict(i=r["id"]))
        r["last_contact"] = li; r["days"] = (datetime.date.fromisoformat(r["next_followup"]) - today).days
        r["when"] = "overdue" if r["next_followup"] < t else "today" if r["next_followup"] == t else "soon"
    return dict(today=t, overdue=[r for r in rows if r["when"] == "overdue"], due_today=[r for r in rows if r["when"] == "today"], soon=[r for r in rows if r["when"] == "soon"])

def timeline(c, donor_id):
    d = logic.one(c, "SELECT * FROM donors WHERE id=:i", dict(i=donor_id))
    if not d: return None
    ev = []
    for r in logic.rows(c, "SELECT id, date, amount, purpose, mode, receipt_no FROM donations WHERE donor_id=:i", dict(i=donor_id)):
        ev.append(dict(date=r["date"], kind="Gift", title=f"Gift of ₹{int(r['amount']):,}", detail=" · ".join(x for x in (r["purpose"], r["mode"], r["receipt_no"]) if x)))
    for r in logic.rows(c, "SELECT * FROM interactions WHERE donor_id=:i", dict(i=donor_id)):
        ev.append(dict(date=r["date"], kind=r["channel"] or "Contact", title=(r["outcome"] or "Contact") + (" (they called)" if r["direction"] == "In" else ""), detail=r["summary"] + (f" · by {r['owner']}" if r["owner"] else "")))
    for r in logic.rows(c, """SELECT ts, kind, subject, status FROM email_log WHERE (tbl='donors' AND row_id=:i) OR (tbl='donations' AND row_id IN (SELECT id FROM donations WHERE donor_id=:i))""", dict(i=donor_id)):
        ev.append(dict(date=r["ts"][:10], kind="Email", title=f"{r['kind'].title()} email {r['status']}", detail=r["subject"] or ""))
    ev.sort(key=lambda e: e["date"] or "", reverse=True)
    return dict(donor=dict(id=d["id"], name=d["name"], code=d["code"], phone=d["phone"], email=d["email"], next_followup=d["next_followup"]), events=ev[:200])

# ------------------------------------------------------------------ logo
def save_logo(c, data_url):
    m = re.fullmatch(r"data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=\s]+)", data_url or "")
    if not m: raise ValueError("Use a PNG, JPG, WEBP or GIF image")
    raw = base64.b64decode(m.group(2), validate=False)
    if len(raw) > 300_000: raise ValueError("Logo is too big. Keep it under 300 KB.")
    magic = dict(png=raw[:8] == b"\x89PNG\r\n\x1a\n", jpeg=raw[:3] == b"\xff\xd8\xff", webp=raw[:4] == b"RIFF" and raw[8:12] == b"WEBP", gif=raw[:4] in (b"GIF8",))
    if not magic[m.group(1)]: raise ValueError("That file is not a real " + m.group(1).upper() + " image")
    c.execute("INSERT OR REPLACE INTO assets(name,mime,data) VALUES('logo',?,?)", ("image/" + m.group(1), raw))
    ver = str(int(time.time())); c.execute("INSERT OR REPLACE INTO settings VALUES('brand_logo_ver',?)", (ver,)); return ver

def remove_logo(c):
    c.execute("DELETE FROM assets WHERE name='logo'"); c.execute("INSERT OR REPLACE INTO settings VALUES('brand_logo_ver','')")

def get_logo(c):
    r = c.execute("SELECT mime, data FROM assets WHERE name='logo'").fetchone()
    return (bytes(r["data"]), r["mime"]) if r else None

def lum(hexc):
    r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda x: x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)
