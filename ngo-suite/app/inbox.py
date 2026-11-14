"""Replies from donors by WhatsApp or SMS: webhook receivers (Meta Cloud API, Twilio, or any provider through a secret link),
a shared inbox, and STOP handling that is applied at once and remembered even for numbers not in the database."""
import hmac, hashlib, base64, json, re, datetime, urllib.parse
from . import db, gateway, logic

class InboxError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg); self.status, self.msg = status, msg

STOP = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "optout", "opt out", "stop all", "unsub"}
START = {"start", "unstop", "subscribe", "resume"}
WINDOW_HOURS = 24

def _now(): return datetime.datetime.now().isoformat(timespec="seconds")
def _key(p): return gateway.normalise_phone(p) or re.sub(r"\D", "", p or "")
def _word(t): return re.sub(r"[^a-z ]", "", (t or "").lower()).strip()

# ------------------------------------------------------------------ signatures
def meta_ok(secret, raw, header):
    if not secret or not header or not header.startswith("sha256="): return False
    return hmac.compare_digest(hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(), header[7:])

def twilio_ok(token, url, params, header):
    if not token or not header: return False
    data = url + "".join(k + params[k] for k in sorted(params))
    return hmac.compare_digest(base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode(), header)

# ------------------------------------------------------------------ parsing
def parse_meta(payload):
    msgs, stats = [], []
    for e in payload.get("entry", []) or []:
        for ch in e.get("changes", []) or []:
            v = ch.get("value") or {}
            names = {x.get("wa_id"): (x.get("profile") or {}).get("name") for x in v.get("contacts", []) or []}
            for m in v.get("messages", []) or []:
                t = m.get("type"); body = ""
                if t == "text": body = (m.get("text") or {}).get("body", "")
                elif t == "button": body = (m.get("button") or {}).get("text", "")
                elif t == "interactive":
                    i = m.get("interactive") or {}; body = ((i.get("button_reply") or i.get("list_reply") or {}).get("title")) or ""
                else: body = f"[{t or 'message'} received: open it in your WhatsApp app]"
                msgs.append(dict(phone=m.get("from"), text=body, name=names.get(m.get("from")), id=m.get("id"), channel="whatsapp"))
            for st in v.get("statuses", []) or []: stats.append(dict(id=st.get("id"), status=st.get("status")))
    return msgs, stats

def parse_twilio(f):
    frm = f.get("From", ""); ch = "whatsapp" if frm.startswith("whatsapp:") else "sms"
    return [dict(phone=frm.replace("whatsapp:", ""), text=f.get("Body", ""), name=f.get("ProfileName"), id=f.get("MessageSid"), channel=ch)]

def parse_generic(d, channel="whatsapp"):
    g = lambda *ks: next((str(d[k]) for k in ks if d.get(k) not in (None, "")), "")
    ph = g("from", "mobile", "sender", "msisdn", "phone", "From")
    if not ph: raise InboxError(400, "No sender number found (expected from, mobile, sender or phone)")
    ch = g("channel").lower(); ch = ch if ch in ("sms", "whatsapp") else channel
    return [dict(phone=ph, text=g("text", "message", "body", "content", "Body"), name=g("name", "profile_name"), id=g("id", "message_id", "messageId"), channel=ch)]

# ------------------------------------------------------------------ people and opt-out
def people(c, phone):
    k = _key(phone); out = []
    for t, kind in (("donors", "donor"), ("contacts", "contact")):
        for r in c.execute(f"SELECT id, name, phone FROM {t} WHERE COALESCE(phone,'')<>''"):
            if _key(r["phone"]) == k: out.append(dict(kind=kind, id=r["id"], name=r["name"]))
    return out

def opted_out(c):
    return {r["phone"] for r in c.execute("SELECT phone FROM optout")}

def set_consent(c, phone, value):
    for p in people(c, phone):
        c.execute(f"UPDATE {'donors' if p['kind'] == 'donor' else 'contacts'} SET msg_optin=? WHERE id=?", (value, p["id"]))

# ------------------------------------------------------------------ receiving
def receive(c, s, msgs, stats=()):
    """Store incoming messages. Returns dict(stored, stops, starts). Safe to call twice with the same message."""
    stored = stops = starts = 0
    for st in stats:
        if st.get("id") and st.get("status"):
            c.execute("UPDATE messages SET delivery=? WHERE provider_id=?", (st["status"], st["id"])); c.execute("UPDATE inbox SET delivery=? WHERE provider_id=? AND direction='out'", (st["status"], st["id"]))
    for m in msgs:
        k = _key(m.get("phone"))
        if not k: continue
        text = (m.get("text") or "")[:2000]; ch = m.get("channel") if m.get("channel") in ("whatsapp", "sms") else "whatsapp"
        if m.get("id") and c.execute("SELECT 1 FROM inbox WHERE provider_id=? AND direction='in'", (m["id"],)).fetchone(): continue
        w = _word(text); kind = "stop" if w in STOP else "start" if w in START else "message"
        ppl = people(c, k); donor = next((p["id"] for p in ppl if p["kind"] == "donor"), None); contact = next((p["id"] for p in ppl if p["kind"] == "contact"), None)
        name = m.get("name") or (ppl[0]["name"] if ppl else "")
        c.execute("INSERT INTO inbox(ts,channel,phone,direction,name,text,kind,provider_id,read,donor_id,contact_id) VALUES(?,?,?,?,?,?,?,?,0,?,?)", (_now(), ch, k, "in", name, text, kind, m.get("id") or None, donor, contact))
        c.execute("INSERT OR IGNORE INTO inbox_threads(channel,phone) VALUES(?,?)", (ch, k))
        if kind == "stop":
            c.execute("INSERT OR REPLACE INTO optout(phone,ts,source) VALUES(?,?,?)", (k, _now(), ch)); set_consent(c, k, "N"); stops += 1
            if s.get("inbound_stop_reply", "Yes") == "Yes":
                try:
                    pid = gateway.send(s, ch, k, s.get("inbound_stop_text") or "You have been unsubscribed.")
                    c.execute("INSERT INTO inbox(ts,channel,phone,direction,text,kind,provider_id,read,user) VALUES(?,?,?,?,?,?,?,1,?)", (_now(), ch, k, "out", s.get("inbound_stop_text"), "auto", pid or None, "automatic"))
                except gateway.GatewayError: pass
            c.execute("UPDATE inbox SET read=1 WHERE channel=? AND phone=? AND kind='stop'", (ch, k))
        elif kind == "start":
            c.execute("DELETE FROM optout WHERE phone=?", (k,)); set_consent(c, k, "Y"); starts += 1
            c.execute("UPDATE inbox SET read=1 WHERE channel=? AND phone=? AND kind='start'", (ch, k))
        else:
            c.execute("UPDATE inbox_threads SET status='Open' WHERE channel=? AND phone=?", (ch, k))
        stored += 1
    return dict(stored=stored, stops=stops, starts=starts)

# ------------------------------------------------------------------ the inbox
def unread(c):
    return c.execute("SELECT COUNT(*) FROM inbox WHERE direction='in' AND read=0 AND kind='message'").fetchone()[0]

def threads(c, status=""):
    rows = logic.rows(c, """SELECT i.channel, i.phone, MAX(i.id) last_id, SUM(CASE WHEN i.direction='in' AND i.read=0 AND i.kind='message' THEN 1 ELSE 0 END) unread,
                            COALESCE(t.status,'Open') status, t.assignee FROM inbox i LEFT JOIN inbox_threads t ON t.channel=i.channel AND t.phone=i.phone
                            GROUP BY i.channel, i.phone ORDER BY unread>0 DESC, last_id DESC LIMIT 200""")
    out = []
    for r in rows:
        if status and r["status"] != status: continue
        last = logic.one(c, "SELECT text, ts, direction, name FROM inbox WHERE id=:i", dict(i=r["last_id"]))
        nm = logic.one(c, "SELECT name FROM inbox WHERE channel=:c AND phone=:p AND COALESCE(name,'')<>'' ORDER BY id DESC LIMIT 1", dict(c=r["channel"], p=r["phone"]))
        ppl = people(c, r["phone"])
        out.append(dict(r, name=(ppl[0]["name"] if ppl else (nm["name"] if nm else "")), known=bool(ppl), last_text=last["text"], last_ts=last["ts"], last_dir=last["direction"], optout=r["phone"] in opted_out(c)))
    return out

def thread(c, channel, phone, mark_read=True):
    k = _key(phone)
    msgs = logic.rows(c, "SELECT id, ts, direction, text, kind, delivery, user, name FROM inbox WHERE channel=:c AND phone=:p ORDER BY id", dict(c=channel, p=k))
    if not msgs: raise InboxError(404, "Conversation not found")
    if mark_read: c.execute("UPDATE inbox SET read=1 WHERE channel=? AND phone=? AND direction='in'", (channel, k))
    ppl = people(c, k); t = logic.one(c, "SELECT status, assignee FROM inbox_threads WHERE channel=:c AND phone=:p", dict(c=channel, p=k)) or {}
    last_in = next((m["ts"] for m in reversed(msgs) if m["direction"] == "in" and m["kind"] == "message"), None)
    open_win = bool(last_in) and (datetime.datetime.now() - datetime.datetime.fromisoformat(last_in)).total_seconds() < WINDOW_HOURS * 3600
    return dict(channel=channel, phone=k, people=ppl, status=t.get("status") or "Open", assignee=t.get("assignee"), optout=k in opted_out(c), can_reply=(open_win if channel == "whatsapp" else True), messages=msgs)

def reply(c, s, user, channel, phone, text):
    k = _key(phone); text = (text or "").strip()
    if not text: raise InboxError(400, "Write a message first")
    if len(text) > 1500: raise InboxError(400, "Message is too long")
    if k in opted_out(c): raise InboxError(400, "This person replied STOP. Do not message them unless they send START.")
    t = thread(c, channel, k, mark_read=False)
    if channel == "whatsapp" and not t["can_reply"]: raise InboxError(400, "WhatsApp allows a free-text reply only within 24 hours of their last message. Send an approved template from Broadcast instead.")
    try: pid = gateway.send(s, channel, k, text)
    except gateway.GatewayError as e: raise InboxError(400, str(e))
    c.execute("INSERT INTO inbox(ts,channel,phone,direction,text,kind,provider_id,read,user) VALUES(?,?,?,?,?,?,?,1,?)", (_now(), channel, k, "out", text, "message", pid or None, user.get("name") or user["username"]))
    return dict(ok=True)

def set_thread(c, channel, phone, status=None, assignee=None):
    k = _key(phone); c.execute("INSERT OR IGNORE INTO inbox_threads(channel,phone) VALUES(?,?)", (channel, k))
    if status is not None:
        if status not in ("Open", "Done"): raise InboxError(400, "Status must be Open or Done")
        c.execute("UPDATE inbox_threads SET status=? WHERE channel=? AND phone=?", (status, channel, k))
    if assignee is not None:
        if assignee and not c.execute("SELECT 1 FROM users WHERE username=? AND active=1 AND role IN ('admin','accountant','programme')", (assignee,)).fetchone(): raise InboxError(400, "Choose a user from the list")
        c.execute("UPDATE inbox_threads SET assignee=? WHERE channel=? AND phone=?", (assignee or None, channel, k))
