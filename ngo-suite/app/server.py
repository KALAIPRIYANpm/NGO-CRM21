"""HTTP server (standard library only): JSON API + static front-end."""
import gzip, hashlib, json, os, re, csv, io, secrets, time, datetime, sqlite3, mimetypes, shutil, tempfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
from . import automation, comms, db, gateway, logic, mailer, media, claims, pwa, vault, qr, cards, compliance_pack, inbox, securebackup, journey, donorcare, dedupe, weekly, csr, langpack, partners, v12, v13, v14, v10, notify
from .spec import TABLES, meta, ALL
from .mailer import EMAIL_RE

VERSION = "v14 (CSR proposal, official documents, yearly plan, social posts)"
STATIC = os.path.join(os.path.dirname(__file__), "static")
SESSION_HOURS = 12
ROLES = ["admin", "accountant", "programme", "viewer"]
ROLE_LABEL = {"admin": "Administrator", "accountant": "Accounts & fundraising", "programme": "Programme & field", "viewer": "View only"}
REF_LABEL = {"media": ("id", "caption"), "donors": ("code", "name"), "projects": ("name", None), "team": ("code", "name"), "grants": ("code", "funder"),
             "funds": ("name", None), "records": ("record_no", "party"), "beneficiaries": ("code", "name"), "partners": ("code", "name"), "partner_events": ("title", "date")}
_fails = {}
_pre = {}

_static_cache = {}
def _static_bytes(fp, tag, gz):
    k = (fp, tag, gz)
    if k not in _static_cache:
        for old in [x for x in _static_cache if x[0] == fp]: _static_cache.pop(old, None)
        with open(fp, "rb") as fh: raw = fh.read()
        _static_cache[k] = gzip.compress(raw, 6) if gz else raw
    return _static_cache[k]

class FileResp:
    """A file on disk, streamed with HTTP Range support (needed for video seeking on phones)."""
    def __init__(self, path, mime, name, cache="private, max-age=300"):
        self.path, self.mime, self.name, self.cache = path, mime, name, cache

class ApiError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg); self.status, self.msg = status, msg

# ------------------------------------------------------------------ validation
def _num(v, label, integer=False):
    if v in (None, ""): return 0
    try:
        x = float(str(v).replace(",", ""))
    except ValueError:
        raise ApiError(400, f"{label}: '{v}' is not a number")
    if x < 0 or x != x or x == float("inf"): raise ApiError(400, f"{label} cannot be negative")
    return int(x) if integer else round(x, 2)

def clean(c, spec, data, partial=False):
    out = {}
    for f in spec["fields"]:
        k, t, lab = f["k"], f["t"], f["l"]
        if k not in data:
            if f.get("req") and not partial: raise ApiError(400, f"{lab} is required")
            continue
        v = data[k]
        if isinstance(v, str): v = v.strip()
        if t in ("text", "area") or t.startswith("list:"):
            v = (v or "")
            if len(v) > 2000: raise ApiError(400, f"{lab} is too long")
        elif t == "int": v = _num(v, lab, True)
        elif t == "num": v = _num(v, lab)
        elif t == "date":
            if v in (None, ""): v = None
            else:
                try: datetime.date.fromisoformat(v)
                except (ValueError, TypeError): raise ApiError(400, f"{lab}: use a date like 2026-04-01")
        elif t.startswith("enum:"):
            opts = t[5:].split(",")
            if v in (None, ""):
                v = None
            elif v not in opts: raise ApiError(400, f"{lab} must be one of {', '.join(opts)}")
        elif t.startswith("ref:"):
            if v in (None, "", 0, "0"): v = None
            else:
                try: v = int(v)
                except (ValueError, TypeError): raise ApiError(400, f"{lab}: invalid choice")
                if not c.execute(f"SELECT 1 FROM {t[4:]} WHERE id=?", (v,)).fetchone(): raise ApiError(400, f"{lab}: that record does not exist")
        if f.get("req") and v in (None, "", 0) and t not in ("num", "int"): raise ApiError(400, f"{lab} is required")
        if f.get("req") and t in ("num", "int") and v in (None, "") : raise ApiError(400, f"{lab} is required")
        out[k] = v
    return out

def next_code(c, table, col, prefix, start, pad=0):
    mx = None
    for (v,) in c.execute(f"SELECT {col} FROM {table} WHERE {col} LIKE ?", (prefix + "%",)):
        m = re.fullmatch(re.escape(prefix) + r"(\d+)", v or "")
        if m: mx = max(mx or 0, int(m.group(1)))
    n = start if mx is None else mx + 1
    return f"{prefix}{n:0{pad}d}" if pad else f"{prefix}{n}"

def autocode(c, spec, rec):
    col = spec.get("code")
    if col and not rec.get(col):
        if spec["name"] == "team":
            vol = rec.get("pay_type") == "Volunteer"
            rec[col] = next_code(c, "team", "code", "V-" if vol else "S-", 1, 2)
        else:
            rec[col] = next_code(c, spec["name"], col, spec["prefix"], spec["start"], spec.get("pad", 0))
    if spec["name"] == "cash_book" and not rec.get("voucher_no"):
        rec["voucher_no"] = next_code(c, "cash_book", "voucher_no", "RC-" if rec.get("type") == "Receipt" else "PM-", 101)

# ------------------------------------------------------------------ cash-book posting
def sync_cash(c, table, rid):
    src = f"{table}:{rid}"
    c.execute("DELETE FROM cash_book WHERE source=?", (src,))
    r = c.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone()
    if not r or not r["fund_id"]: return
    if table == "donations":
        party = c.execute("SELECT name FROM donors WHERE id=?", (r["donor_id"],)).fetchone()["name"]
        row = ("Receipt", "Donations", party, r["mode"], r["receipt_no"], r["purpose"])
    elif table == "instalments":
        party = c.execute("SELECT funder FROM grants WHERE id=?", (r["grant_id"],)).fetchone()["funder"]
        row = ("Receipt", "Grant Received", party, None, r["reference"], r["note"])
    else:
        row = ("Payment", r["head"] or "Other", r["paid_to"], None, r["voucher_no"], "Grant spend")
    c.execute("INSERT INTO cash_book(date,voucher_no,type,fund_id,head,party,mode,amount,note,source) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (r["date"], row[4], row[0], r["fund_id"], row[1], row[2], row[3], r["amount"], row[5], src))

POSTING = ("donations", "instalments", "grant_spend")

def check_rules(c, name, rec):
    if name == "donations" and rec.get("fund_id"):
        f = c.execute("SELECT type, name FROM funds WHERE id=?", (rec["fund_id"],)).fetchone()
        if rec.get("fund_type") and rec["fund_type"] != f["type"]:
            raise ApiError(400, f"This gift is {rec['fund_type']} but fund '{f['name']}' is {f['type']}. Pick a matching fund.")
    if name == "social_posts":
        if rec.get("media_id"):
            m = c.execute("SELECT consent FROM media WHERE id=?", (rec["media_id"],)).fetchone()
            if not m or m["consent"] != "Y": raise ApiError(400, "That photo or video has no consent recorded. Pick one with consent, or record consent first.")
        if rec.get("status") in ("Approved", "Posted"):
            ap = (rec.get("approved_by") or "").strip()
            if not ap: raise ApiError(400, "Say who approved this post before marking it Approved or Posted.")
            if ap.lower() == (rec.get("owner") or "").strip().lower(): raise ApiError(400, "A different person must approve the post.")
        if rec.get("status") == "Posted" and not rec.get("posted_on"): raise ApiError(400, "Add the date it was posted.")
        if rec.get("names_ok") != "Y":
            txt = ((rec.get("caption") or "") + " " + (rec.get("title") or "")).lower()
            for t in ("donors", "beneficiaries"):
                for r in c.execute(f"SELECT name FROM {t}"):
                    n = (r["name"] or "").strip()
                    if len(n) >= 4 and n.lower() in txt:
                        raise ApiError(400, f"The post names {n}. Remove the name, or tick that the person agreed.")
    if name in ("projects", "grants") and rec.get("start") and rec.get("end") and rec["end"] < rec["start"]:
        raise ApiError(400, "End date is before the start date")
    if name == "team" and rec.get("pay_type") == "Volunteer": rec["pay_rate"] = 0
    if name in ("attendance", "volunteer_log"):
        m = c.execute("SELECT pay_type FROM team WHERE id=?", (rec.get("team_id"),)).fetchone()
        if name == "volunteer_log" and m and m["pay_type"] != "Volunteer":
            raise ApiError(400, "The Volunteer Log is for volunteers only. Use Daily Attendance for staff.")
        if name == "attendance" and m and m["pay_type"] == "Volunteer":
            raise ApiError(400, "Volunteers do not have attendance pay. Use the Volunteer Log.")

# ------------------------------------------------------------------ CRUD
def list_rows(c, name, q):
    spec = TABLES[name]
    s, today, P = logic.ctx(c)
    sql, params, where = spec["sql"], dict(P), []
    if q.get("q"):
        like = []
        for i, col in enumerate(spec["search"]):
            col = col if "." in col else "t." + col
            like.append(f"{col} LIKE :q{i}"); params[f"q{i}"] = f"%{q['q'][0]}%"
        if like: where.append("(" + " OR ".join(like) + ")")
    fields = {f["k"] for f in spec["fields"]}
    for key, vals in q.items():
        if key.startswith("f_") and key[2:] in fields:
            where.append(f"t.{key[2:]} = :{key}"); params[key] = vals[0]
    if "date" in fields:
        if q.get("from"): where.append("t.date >= :dfrom"); params["dfrom"] = q["from"][0]
        if q.get("to"): where.append("t.date <= :dto"); params["dto"] = q["to"][0]
    if where: sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + spec["order"]
    lim = min(int(q.get("limit", ["5000"])[0]), 20000)
    out = [dict(r) for r in c.execute(sql + f" LIMIT {lim}", params)]
    if name == "grants":
        for g in out: g["pace"] = logic.grant_pace(g, P["grant_slow_gap"])
    if name == "compliance":
        for g in out: g.update(logic.compliance_status(g, today))
        out.sort(key=lambda g: (g["next_due"] or "9"))
    return out

def get_row(c, name, rid):
    s, today, P = logic.ctx(c)
    r = c.execute(TABLES[name]["sql"] + " WHERE t.id=:id", {**P, "id": rid}).fetchone()
    if not r: raise ApiError(404, "Not found")
    return dict(r)

def create(c, name, data, user):
    spec = TABLES[name]
    rec = clean(c, spec, data)
    check_rules(c, name, rec)
    autocode(c, spec, rec)
    if name == "journey" and not rec.get("recorded_by"): rec["recorded_by"] = user.get("name") or user["username"]
    cols = list(rec)
    try:
        cur = c.execute(f"INSERT INTO {name}({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [rec[k] for k in cols])
    except sqlite3.IntegrityError as e:
        raise ApiError(400, friendly(e))
    if name in POSTING: sync_cash(c, name, cur.lastrowid)
    if name == "interactions": sync_followup(c, cur.lastrowid)
    if name == "event_people": v10.sync_event(c, rec["event_id"])
    audit(c, user, "create", name, cur.lastrowid, rec)
    return cur.lastrowid

def update(c, name, rid, data, user):
    spec = TABLES[name]
    old = c.execute(f"SELECT * FROM {name} WHERE id=?", (rid,)).fetchone()
    if not old: raise ApiError(404, "Not found")
    if name == "cash_book" and old["source"]:
        raise ApiError(400, f"This entry was posted from {old['source'].split(':')[0].replace('_', ' ')}. Edit it there.")
    rec = clean(c, spec, data, partial=True)
    merged = {**dict(old), **rec}
    check_rules(c, name, merged); rec = {k: merged[k] for k in rec} | ({"pay_rate": merged["pay_rate"]} if name == "team" else {})
    if not rec: return
    try:
        c.execute(f"UPDATE {name} SET {','.join(k + '=?' for k in rec)} WHERE id=?", [*rec.values(), rid])
    except sqlite3.IntegrityError as e:
        raise ApiError(400, friendly(e))
    if name in POSTING: sync_cash(c, name, rid)
    if name == "interactions": sync_followup(c, rid)
    if name == "event_people": v10.sync_event(c, merged["event_id"])
    audit(c, user, "update", name, rid, rec)

def delete(c, name, rid, user):
    old = c.execute(f"SELECT * FROM {name} WHERE id=?", (rid,)).fetchone()
    if not old: raise ApiError(404, "Not found")
    if name == "cash_book" and old["source"]:
        raise ApiError(400, f"This entry was posted from {old['source'].split(':')[0].replace('_', ' ')}. Delete it there.")
    try:
        if name in POSTING: c.execute("DELETE FROM cash_book WHERE source=?", (f"{name}:{rid}",))
        c.execute(f"DELETE FROM {name} WHERE id=?", (rid,))
    except sqlite3.IntegrityError:
        raise ApiError(400, "This record is used by other records. Delete or change those first.")
    if name == "event_people": v10.sync_event(c, old["event_id"])
    if name == "official_docs" and old["file"]: media.remove_files(old["file"])
    audit(c, user, "delete", name, rid, dict(old))

def sync_followup(c, rid):
    r = c.execute("SELECT * FROM interactions WHERE id=?", (rid,)).fetchone()
    if not r: return
    last = c.execute("SELECT id FROM interactions WHERE donor_id=? ORDER BY date DESC, id DESC LIMIT 1", (r["donor_id"],)).fetchone()
    if last and last["id"] == rid: c.execute("UPDATE donors SET next_followup=? WHERE id=?", (r["next_followup"] or "", r["donor_id"]))

def friendly(e):
    m = str(e)
    if "UNIQUE" in m:
        return "That value already exists" + (" (same date and team member already has an entry)" if "attendance" in m else "")
    if "FOREIGN" in m: return "Choose a valid linked record"
    return "Could not save: " + m

def hmac_ok(user, pw):
    import hmac as _hm
    h, _ = db.hash_pw(pw or "", user["salt"])
    return _hm.compare_digest(h, user["pw_hash"])

def audit(c, user, action, tbl, rid, detail):
    c.execute("INSERT INTO audit(ts,user,action,tbl,row_id,detail) VALUES(?,?,?,?,?,?)",
              (datetime.datetime.now().isoformat(timespec="seconds"), user["username"], action, tbl, rid, json.dumps(detail, default=str)[:1500]))

def options(c, name):
    a, b = REF_LABEL[name]
    out = []
    for r in c.execute(f"SELECT * FROM {name} ORDER BY {a}"):
        out.append(dict(id=r["id"], label=r[a] if not b else f"{r[a]} · {r[b]}"))
    return out

# ------------------------------------------------------------------ CSV
def export_csv(c, name):
    spec = TABLES[name]
    rows = list_rows(c, name, {})
    cols = spec["cols"]
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow([x[1] for x in cols])
    for r in rows: w.writerow([r.get(x[0], "") if r.get(x[0]) is not None else "" for x in cols])
    return buf.getvalue()

def import_csv(c, name, text, user, dry=False):
    spec = TABLES[name]
    rdr = csv.DictReader(io.StringIO(text))
    if not rdr.fieldnames: raise ApiError(400, "The file is empty")
    by_key = {}
    for f in spec["fields"]:
        by_key[f["k"].lower()] = f; by_key[f["l"].lower()] = f
        by_key[re.sub(r"\s*\(.*?\)", "", f["l"]).lower().strip()] = f
    mapping = {h: by_key[h.strip().lower()] for h in rdr.fieldnames if h and h.strip().lower() in by_key}
    if not mapping: raise ApiError(400, "No column heading matched. Use the field names shown on the Add form.")
    errors, n = [], 0
    c.execute("SAVEPOINT imp")
    for i, row in enumerate(rdr, start=2):
        data = {}
        for h, f in mapping.items():
            v = (row.get(h) or "").strip()
            if f["t"].startswith("ref:") and v:
                tbl = f["t"][4:]; a, b = REF_LABEL[tbl]
                r = c.execute(f"SELECT id FROM {tbl} WHERE {a}=? OR {b or a}=?", (v, v)).fetchone()
                if not r: errors.append(f"Row {i}: {f['l']} '{v}' not found"); data = None; break
                v = r["id"]
            data[f["k"]] = v
        if data is None: continue
        if not any(str(x).strip() for x in data.values()): continue
        try:
            create(c, name, data, user); n += 1
        except ApiError as e:
            errors.append(f"Row {i}: {e.msg}")
    if errors or dry:
        c.execute("ROLLBACK TO imp"); c.execute("RELEASE imp")
        return dict(imported=0, errors=errors[:30], total_errors=len(errors), dry=bool(dry), would_import=0 if errors else n)
    c.execute("RELEASE imp")
    return dict(imported=n, errors=[])

# ------------------------------------------------------------------ handler
class Handler(BaseHTTPRequestHandler):
    server_version = "NGOSuite/1.0"
    def log_message(self, fmt, *a):
        if os.environ.get("NGO_LOG"): super().log_message(fmt, *a)

    # --- helpers
    def send_json(self, obj, status=200, headers=None):
        body = json.dumps(obj, default=str).encode()
        gz = len(body) > 1024 and "gzip" in (self.headers.get("Accept-Encoding") or "")
        if gz: body = gzip.compress(body, 5)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if gz: self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.sec(); self.end_headers(); self.wfile.write(body)

    def sec(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
        if self.https(): self.send_header("Strict-Transport-Security", "max-age=15552000")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'")

    LOOPBACK = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
    def ip(self):
        """Client address. Behind a proxy on this same computer (Cloudflare Tunnel, Caddy) the real address
        arrives in a header; that header is believed only when the connection comes from this computer."""
        ra = self.client_address[0]
        if ra in self.LOOPBACK:
            fwd = (self.headers.get("CF-Connecting-IP") or (self.headers.get("X-Forwarded-For") or "").split(",")[0]).strip()
            if fwd: return fwd[:64]
        return ra
    def https(self):
        return os.environ.get("NGO_FORCE_SECURE") == "1" or (self.client_address[0] in self.LOOPBACK and (self.headers.get("X-Forwarded-Proto") or "").lower() == "https")
    def cookie(self, tok=None):
        if tok is None: return "ngo_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0" + ("; Secure" if self.https() else "")
        return f"ngo_session={tok}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_HOURS * 3600}" + ("; Secure" if self.https() else "")
    def token(self):
        m = re.search(r"ngo_session=([A-Za-z0-9_\-]+)", self.headers.get("Cookie") or ""); return m.group(1) if m else None
    def start_session(self, c, uid):
        tok = secrets.token_urlsafe(32)
        c.execute("INSERT INTO sessions VALUES(?,?,?)", (tok, uid, datetime.datetime.now().isoformat()))
        c.execute("DELETE FROM sessions WHERE created < ?", ((datetime.datetime.now() - datetime.timedelta(days=2)).isoformat(),))
        return tok

    def raw_body(self, limit=1_000_000):
        n = int(self.headers.get("Content-Length") or 0)
        if n > limit: raise ApiError(413, "Request too large")
        return self.rfile.read(n) if n else b""

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20_000_000: raise ApiError(413, "Request too large")
        raw = self.rfile.read(n) if n else b""
        if not raw: return {}
        if "json" not in (self.headers.get("Content-Type") or ""): raise ApiError(415, "JSON required")
        try: return json.loads(raw)
        except ValueError: raise ApiError(400, "Invalid JSON")

    def user(self, c):
        ck = self.headers.get("Cookie") or ""
        m = re.search(r"ngo_session=([A-Za-z0-9_\-]+)", ck)
        if not m: return None
        r = c.execute("SELECT u.*, s.created FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND u.active=1", (m.group(1),)).fetchone()
        if not r: return None
        if (datetime.datetime.now() - datetime.datetime.fromisoformat(r["created"])).total_seconds() > SESSION_HOURS * 3600:
            c.execute("DELETE FROM sessions WHERE token=?", (m.group(1),)); c.commit(); return None
        d = dict(r); d["totp"] = bool(d.get("totp_secret"))
        pol = c.execute("SELECT value FROM settings WHERE key='require_2fa_admin'").fetchone()
        d["need2fa"] = bool(pol and pol["value"] == "Yes" and d["role"] == "admin" and not d["totp"])
        return d

    def serve_static(self, path):
        if path == "/favicon.ico":
            self.send_response(204); self.end_headers(); return
        if path == "/manifest.webmanifest" or re.fullmatch(r"/icon-(192|512)\.png", path):
            c = db.connect()
            try: st = db.get_settings(c)
            finally: c.close()
            if path.endswith(".png"): data, ct = pwa.icon_png(int(path[6:-4]), st.get("brand_color") or ""), "image/png"
            else: data, ct = pwa.manifest(st), "application/manifest+json"
            self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-cache")
            self.sec(); self.end_headers(); self.wfile.write(data); return
        if path in ("", "/"): path = "/index.html"
        fp = os.path.normpath(os.path.join(STATIC, path.lstrip("/")))
        if not fp.startswith(STATIC) or not os.path.isfile(fp):
            self.send_json({"error": "Not found"}, 404); return
        st = os.stat(fp); tag = '"%x-%x"' % (int(st.st_mtime), st.st_size)
        ctype = (mimetypes.guess_type(fp)[0] or "application/octet-stream") + ("; charset=utf-8" if fp.endswith((".html", ".js", ".css", ".webmanifest")) else "")
        if self.headers.get("If-None-Match") == tag:       # unchanged: the phone keeps its copy, nothing is downloaded
            self.send_response(304); self.send_header("ETag", tag); self.send_header("Cache-Control", "no-cache"); self.sec(); self.end_headers(); return
        gz = fp.endswith((".html", ".js", ".css", ".svg", ".webmanifest")) and "gzip" in (self.headers.get("Accept-Encoding") or "")
        data = _static_bytes(fp, tag, gz)
        self.send_response(200)
        self.send_header("Content-Type", ctype); self.send_header("ETag", tag); self.send_header("Vary", "Accept-Encoding")
        if gz: self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.sec(); self.end_headers(); self.wfile.write(data)

    def send_file(self, fr):
        try: size = os.path.getsize(fr.path)
        except OSError: return self.send_json({"error": "File missing"}, 404)
        start, end, status = 0, size - 1, 200
        rg = self.headers.get("Range") or ""
        m = re.match(r"bytes=(\d*)-(\d*)$", rg.strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1)); end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2))); end = size - 1
            if start >= size or start > end:
                self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.send_header("Content-Length", "0"); self.sec(); self.end_headers(); return
            end = min(end, size - 1); status = 206
        n = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", fr.mime); self.send_header("Content-Length", str(n)); self.send_header("Accept-Ranges", "bytes")
        if status == 206: self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", fr.cache)
        self.send_header("Content-Disposition", f'inline; filename="{fr.name}"')
        self.sec(); self.end_headers()
        if self.command == "HEAD": return
        try:
            with open(fr.path, "rb") as fh:
                fh.seek(start); left = n
                while left > 0:
                    b = fh.read(min(256 * 1024, left))
                    if not b: break
                    self.wfile.write(b); left -= len(b)
        except (BrokenPipeError, ConnectionResetError): pass

    def handle_any(self, method):
        u = urlparse(self.path); path = unquote(u.path); q = parse_qs(u.query)
        if not path.startswith("/api/"):
            if method != "GET": return self.send_json({"error": "Not found"}, 404)
            return self.serve_static(path)
        c = db.connect()
        try:
            try:
                res = self.route(c, method, path, q)
                c.commit()
            except ApiError as e:
                c.rollback(); return self.send_json({"error": e.msg}, e.status)
            except sqlite3.Error as e:
                c.rollback(); return self.send_json({"error": "Database error: " + str(e)}, 500)
            except Exception as e:  # pragma: no cover
                c.rollback(); import traceback; traceback.print_exc()
                return self.send_json({"error": "Server error"}, 500)
            if isinstance(res, FileResp):
                return self.send_file(res)
            if isinstance(res, tuple): # raw (bytes, content-type, filename)
                data, ctype, fname = res
                self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", ("inline" if ctype.startswith(("image/", "text/")) and not ctype.startswith("text/csv") else "attachment") + f'; filename="{fname}"'); self.sec(); self.end_headers(); self.wfile.write(data)
            elif isinstance(res, dict) and "__cookie" in res:
                ck = res.pop("__cookie"); self.send_json(res, headers={"Set-Cookie": ck})
            else:
                self.send_json(res)
        finally:
            c.close()

    do_GET = lambda self: self.handle_any("GET")
    do_POST = lambda self: self.handle_any("POST")
    do_PUT = lambda self: self.handle_any("PUT")
    do_DELETE = lambda self: self.handle_any("DELETE")

    def media_route(self, c, method, path, q, user):
        role = user["role"]; admin = role == "admin"
        parts = path.strip("/").split("/")          # api media [id [file|thumb]]
        if len(parts) == 2:
            if method == "GET": return media.listing(c, user, q)
            if method == "POST":
                if role not in ("admin", "programme"): raise ApiError(403, "Your role cannot upload photos or videos")
                want = "video" if q.get("kind", ["photo"])[0] == "video" else "photo"
                cid = (q.get("client_id", [""])[0] or "")[:60]
                if cid:
                    old = c.execute("SELECT id FROM media WHERE client_id=?", (cid,)).fetchone()
                    if old: self._drain(); return dict(id=old["id"], duplicate=True)
                n = int(self.headers.get("Content-Length") or 0)
                if n > (media.MAX_VIDEO if want == "video" else media.MAX_PHOTO):
                    if n <= 150_000_000: self._drain()      # read it so the phone receives our message, not a dropped connection
                rel, kind, mime, size = media.save_stream(self.rfile, n, want)
                try:
                    mid = media.create(c, user, kind, rel, mime, size, q)
                except BaseException:
                    media.remove_files(rel); raise
                audit(c, user, "create", "media", mid, dict(kind=kind, size=size, project=q.get("project_id", [""])[0]))
                return dict(id=mid)
            raise ApiError(405, "Not allowed")
        if not parts[2].isdigit(): raise ApiError(404, "Not found")
        mid = int(parts[2])
        row = c.execute("SELECT * FROM media WHERE id=?", (mid,)).fetchone()
        if not row or not media.can_see(user, row): raise ApiError(404, "Not found")
        mine = row["uploaded_by"] == user["id"]
        if len(parts) == 4 and method == "GET" and parts[3] in ("file", "thumb"):
            rel = row["file"] if parts[3] == "file" else (row["thumb"] or (row["file"] if row["kind"] == "photo" else None))
            if not rel: raise ApiError(404, "No preview")
            mime = row["mime"] if rel == row["file"] else "image/jpeg"
            return FileResp(media.abspath(rel), mime, os.path.basename(rel))
        if len(parts) == 4 and method == "POST" and parts[3] == "thumb":
            if not (mine or admin): raise ApiError(403, "Not allowed")
            n = int(self.headers.get("Content-Length") or 0)
            rel, _k, _m, _s = media.save_stream(self.rfile, n, "thumb")
            media.remove_files(row["thumb"])
            c.execute("UPDATE media SET thumb=? WHERE id=?", (rel, mid))
            return dict(ok=True)
        if len(parts) == 3 and method == "PUT":
            if not (mine or admin): raise ApiError(403, "Only the person who uploaded it, or an admin, can change this")
            b = self.body(); sets, args = [], []
            if "caption" in b: sets.append("caption=?"); args.append(str(b["caption"] or "")[:300])
            if "consent" in b: sets.append("consent=?"); args.append("Y" if b["consent"] == "Y" else "N")
            if "project_id" in b:
                pid = b["project_id"] or None
                if pid and not c.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone(): raise ApiError(400, "Project not found")
                sets.append("project_id=?"); args.append(pid)
            if sets:
                c.execute(f"UPDATE media SET {','.join(sets)} WHERE id=?", args + [mid])
                audit(c, user, "update", "media", mid, {k: b[k] for k in ("caption", "consent", "project_id") if k in b})
            return dict(ok=True)
        if len(parts) == 3 and method == "DELETE":
            if not (mine or admin): raise ApiError(403, "Only the person who uploaded it, or an admin, can delete this")
            c.execute("DELETE FROM media WHERE id=?", (mid,))
            audit(c, user, "delete", "media", mid, dict(kind=row["kind"], caption=row["caption"]))
            c.commit(); media.remove_files(row["file"], row["thumb"])
            return dict(ok=True)
        raise ApiError(405, "Not allowed")

    def hook_route(self, c, method, path, q):
        """Public endpoints the messaging provider calls. Every one proves the call is genuine before anything is stored."""
        st = db.get_settings(c); g = lambda k: (q.get(k) or [""])[0]
        try:
            if path == "/api/hook/meta" and method == "GET":
                tok = st.get("wa_verify_token") or ""
                if tok and g("hub.mode") == "subscribe" and secrets.compare_digest(g("hub.verify_token"), tok): return g("hub.challenge").encode()[:200], "text/plain", "challenge"
                raise ApiError(403, "Verify token does not match")
            if path == "/api/hook/meta" and method == "POST":
                raw = self.raw_body()
                if not st.get("wa_app_secret"): raise ApiError(403, "Set the WhatsApp App Secret in Settings first")
                if not inbox.meta_ok(st["wa_app_secret"], raw, self.headers.get("X-Hub-Signature-256")): raise ApiError(403, "Bad signature")
                try: payload = json.loads(raw or b"{}")
                except ValueError: raise ApiError(400, "Invalid JSON")
                msgs, stats = inbox.parse_meta(payload if isinstance(payload, dict) else {})
                return dict(ok=True, **inbox.receive(c, st, msgs, stats))
            if path == "/api/hook/twilio" and method == "POST":
                raw = self.raw_body(); f = {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True).items()}
                base = (st.get("public_url") or "").strip().rstrip("/")
                if not base or not st.get("twilio_token"): raise ApiError(403, "Set the public web address and the Twilio token in Settings first")
                if not inbox.twilio_ok(st["twilio_token"], base + "/api/hook/twilio", f, self.headers.get("X-Twilio-Signature")): raise ApiError(403, "Bad signature")
                return dict(ok=True, **inbox.receive(c, st, inbox.parse_twilio(f)))
            if path == "/api/hook/generic" and method == "POST":
                tok = st.get("inbound_token") or ""
                if not tok or not secrets.compare_digest(g("token"), tok): raise ApiError(403, "Bad token")
                raw = self.raw_body(); ct = self.headers.get("Content-Type") or ""
                try: d = json.loads(raw or b"{}") if "json" in ct else {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace")).items()}
                except ValueError: raise ApiError(400, "Invalid JSON")
                if not isinstance(d, dict): raise ApiError(400, "Expected an object")
                return dict(ok=True, **inbox.receive(c, st, inbox.parse_generic(d, g("channel") or "whatsapp")))
        except inbox.InboxError as e: raise ApiError(e.status, e.msg)
        raise ApiError(404, "Not found")

    def inbox_route(self, c, method, path, q, user):
        g = lambda k: (q.get(k) or [""])[0]
        if path == "/api/inbox/count": return dict(unread=inbox.unread(c))
        if path == "/api/inbox/threads" and method == "GET": return inbox.threads(c, g("status"))
        if path == "/api/inbox/thread" and method == "GET": return inbox.thread(c, g("channel"), g("phone"))
        if path == "/api/inbox/assignees": return [dict(username=r["username"], name=r["name"]) for r in c.execute("SELECT username, name FROM users WHERE active=1 AND role IN ('admin','accountant','programme') ORDER BY name")]
        if path == "/api/inbox/reply" and method == "POST":
            b = self.body(); r = inbox.reply(c, db.get_settings(c), user, str(b.get("channel") or ""), str(b.get("phone") or ""), b.get("text")); audit(c, user, "create", "inbox", None, dict(to=str(b.get("phone"))[-4:])); return r
        if path == "/api/inbox/thread" and method == "PUT":
            b = self.body(); inbox.set_thread(c, str(b.get("channel") or ""), str(b.get("phone") or ""), b.get("status"), b.get("assignee")); return {"ok": True}
        if path == "/api/inbox/add-contact" and method == "POST":
            b = self.body(); k = inbox._key(b.get("phone"))
            if not k: raise ApiError(400, "That number does not look right")
            if inbox.people(c, k): raise ApiError(400, "This number is already saved")
            if k in inbox.opted_out(c): raise ApiError(400, "This person replied STOP, so they are saved as not OK for messages")
            rid = create(c, "contacts", dict(name=(b.get("name") or "").strip() or "+" + k, phone="+" + k, msg_optin="N", wishes="N", notes="Added from the inbox. They wrote to us, but have not agreed to broadcasts."), user)
            c.execute("UPDATE inbox SET contact_id=? WHERE phone=?", (rid, k)); return dict(id=rid)
        raise ApiError(404, "Not found")

    def pack_route(self, c, method, path, q, user):
        g = lambda k: (q.get(k) or [""])[0]
        if path == "/api/cards/preview" and method == "GET":
            return cards.build(c, int(g("project_id") or 0), g("month"))
        if path == "/api/cards" and method == "GET": return cards.listing(c)
        if path == "/api/cards" and method == "POST":
            r = cards.create(c, user, self.body()); audit(c, user, "create", "impact_cards", r["id"], dict(url=r["url"][:20])); return r
        m = re.fullmatch(r"/api/cards/(\d+)/revoke", path)
        if m and method == "POST":
            cards.revoke(c, int(m.group(1))); audit(c, user, "update", "impact_cards", int(m.group(1)), dict(revoked=1)); return {"ok": True}
        if path == "/api/pack/readiness": return compliance_pack.readiness(c, g("fy"))
        if path == "/api/pack/register.csv":
            data, name = compliance_pack.register_csv(c, g("fy")); return data, "text/csv; charset=utf-8", name
        if path == "/api/pack/audit-pack":
            data, name = compliance_pack.audit_pack(c, g("fy")); audit(c, user, "export", "audit_pack", None, dict(fy=g("fy"))); return data, "application/zip", name
        m = re.fullmatch(r"/api/pack/donor/(\d+)", path)
        if m: data, name = compliance_pack.donor_statement(c, int(m.group(1)), g("fy")); return data, "text/html; charset=utf-8", name
        m = re.fullmatch(r"/api/pack/uc/(\d+)", path)
        if m: data, name = compliance_pack.utilisation(c, int(m.group(1))); return data, "text/html; charset=utf-8", name
        raise ApiError(404, "Not found")

    def v10_route(self, c, method, path, q, user):
        fin = user["role"] in ("admin", "accountant")
        m = re.fullmatch(r"/api/donors/(\d+)/portal", path)
        if m and method == "POST":
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            body = self.body(); r = v10.set_donor_portal(c, int(m.group(1)), revoke=bool(body.get("revoke")))
            audit(c, user, "portal_off" if body.get("revoke") else "portal_on", "donors", int(m.group(1)), {}); return r
        if path == "/api/yearcheck" and method == "GET":
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            return v10.year_check(c)
        if path == "/api/yearcheck/starter" and method == "POST":
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            r = v10.add_standard_calendar(c); audit(c, user, "create", "compliance", 0, r); return r
        if path == "/api/policies/starter" and method == "POST":
            if user["role"] not in ("admin", "accountant", "programme"): raise ApiError(403, "Not allowed")
            r = v10.add_standard_policies(c); audit(c, user, "create", "policies", 0, r); return r
        if path in ("/api/social/draft", "/api/social/ideas") and method == "GET":
            if user["role"] not in ("admin", "accountant", "programme"): raise ApiError(403, "Not allowed")
            return v12.draft(c, q) if path.endswith("draft") else v12.ideas(c)
        if path == "/api/yearplan" and method == "GET":
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            return v13.yearplan(c)
        if path == "/api/yearplan/starter" and method == "POST":
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            r = v13.add_standard_plan(c); audit(c, user, "create", "plan_calendar", 0, r); return r
        if path == "/api/notifications" and method == "GET":
            try: d = max(1, min(60, int((q.get("days") or ["14"])[0])))
            except ValueError: d = 14
            return notify.build(c, user["role"], d)
        if path == "/api/proposal" and method == "GET":
            if user["role"] not in ("admin", "accountant", "programme"): raise ApiError(403, "Not allowed")
            g = lambda k: (q.get(k) or [""])[0]
            data, name = v14.proposal(c, int(g("project_id") or 0), g("company")[:120], g("ask"), g("months"), g("clause"), g("notes")[:1500])
            audit(c, user, "export", "csr_proposal", int(g("project_id") or 0), dict(company=g("company")[:60]))
            return data, "text/html; charset=utf-8", name
        if path.startswith("/api/odocs"):
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            if path == "/api/odocs/starter" and method == "POST":
                r = v14.add_standard_docs(c); audit(c, user, "create", "official_docs", 0, r); return r
            m = re.fullmatch(r"/api/odocs/(\d+)/file", path)
            if not m: raise ApiError(404, "Not found")
            row = c.execute("SELECT * FROM official_docs WHERE id=?", (int(m.group(1)),)).fetchone()
            if not row: raise ApiError(404, "Not found")
            if method == "GET":
                if not row["file"]: raise ApiError(404, "No file attached")
                return FileResp(media.abspath(row["file"]), row["mime"] or "application/octet-stream", row["file_name"] or os.path.basename(row["file"]))
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n > v14.MAX_DOC and n <= 150_000_000: self._drain()
                rel, mime, size = v14.save_doc(self.rfile, n)
                name = re.sub(r"[^A-Za-z0-9._ -]", "", (q.get("name", [""])[0] or "document"))[:80] or "document"
                old = row["file"]
                try: c.execute("UPDATE official_docs SET file=?, file_name=?, mime=?, size=?, status=CASE WHEN status='Missing' THEN 'Have' ELSE status END WHERE id=?", (rel, name, mime, size, row["id"]))
                except BaseException: media.remove_files(rel); raise
                media.remove_files(old); audit(c, user, "update", "official_docs", row["id"], dict(file=name, size=size)); return dict(ok=True, size=size)
            if method == "DELETE":
                media.remove_files(row["file"]); c.execute("UPDATE official_docs SET file=NULL, file_name=NULL, mime=NULL, size=0 WHERE id=?", (row["id"],))
                audit(c, user, "update", "official_docs", row["id"], dict(file="removed")); return dict(ok=True)
        raise ApiError(404, "Not found")

    def v9_route(self, c, method, path, q, user):
        g = lambda k: (q.get(k) or [""])[0]
        role = user["role"]; fin = role in ("admin", "accountant"); prog = role in ("admin", "programme")
        if path == "/api/partners/pipeline":
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            return partners.pipeline(c)
        m = re.fullmatch(r"/api/partners/event-note/(\d+)", path)
        if m:
            if not (fin or prog): raise ApiError(403, "Not allowed")
            return partners.event_note(c, int(m.group(1)))
        m = re.fullmatch(r"/api/partners/(\d+)/portal", path)
        if m and method == "POST":
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            body = self.body(); r = partners.set_portal(c, int(m.group(1)), revoke=bool(body.get("revoke")))
            audit(c, user, "portal_off" if body.get("revoke") else "portal_on", "partners", int(m.group(1)), {})
            return r
        if path == "/api/relations":
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            return partners.relations(c)
        if path == "/api/funders/tracker":
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            return partners.tracker(c)
        if path == "/api/forecast":
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            return partners.forecast(c, int(g("months") or 12) if g("months").isdigit() or not g("months") else 12)
        if path == "/api/board":
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            return partners.board(c)
        if path == "/api/boardpack":
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            data, name = partners.board_html(c, g("notes")[:1500]); audit(c, user, "export", "board_pack", None, {})
            return data, "text/html; charset=utf-8", name
        raise ApiError(404, "Not found")

    def v8_route(self, c, method, path, q, user):
        g = lambda k: (q.get(k) or [""])[0]
        role = user["role"]; admin = role == "admin"; fin = role in ("admin", "accountant"); prog = role in ("admin", "programme")
        # ---- password-protected backups and restore (administrators only)
        if path.startswith("/api/backup/"):
            if not admin: raise ApiError(403, "Administrators only")
            if path == "/api/backup/list": return dict(files=automation.list_backups(), encrypted=db.get_settings(c).get("backup_encrypt") == "Yes")
            if path == "/api/backup/encrypted" and method == "POST":
                pw = str(self.body().get("password") or "")
                blob = securebackup.make(c, pw); audit(c, user, "backup_download", "backup", None, dict(protected=True))
                return blob, "application/octet-stream", f"ngo-backup-{datetime.date.today()}.ngobk"
            m = re.fullmatch(r"/api/backup/file/((?:ngo-\d{4}-\d{2}-\d{2}\.(?:db|ngobk))|(?:before-restore-[\d-]+\.db))", path)
            if m:
                fp = os.path.join(automation.backup_dir(), m.group(1))
                if not os.path.isfile(fp): raise ApiError(404, "Not found")
                with open(fp, "rb") as fh: data = fh.read()
                audit(c, user, "backup_download", "backup", None, dict(file=m.group(1))); return data, "application/octet-stream", m.group(1)
            if path == "/api/backup/restore" and method == "POST":
                if self.headers.get("X-Confirm") != "RESTORE": raise ApiError(400, "Type RESTORE to confirm")
                if not hmac_ok(user, self.headers.get("X-Admin-Password") or ""): self._drain(); raise ApiError(403, "Your administrator password is not right")
                blob = self.raw_body(limit=250_000_000)
                if not blob: raise ApiError(400, "Choose a backup file")
                audit(c, user, "restore_started", "backup", None, dict(size=len(blob))); c.commit()
                r = securebackup.restore(c, blob, self.headers.get("X-Backup-Password") or "", user["username"])
                return r
            raise ApiError(404, "Not found")
        # ---- beneficiary journey
        if path.startswith("/api/journey/"):
            if method != "GET": raise ApiError(405, "Use the Journey steps register to add steps")
            if path == "/api/journey/people": return journey.people_list(c, g("q"), int(g("project_id") or 0))
            if path == "/api/journey/summary": return journey.summary(c, int(g("project_id") or 0))
            if path == "/api/journey/stale": return journey.stale(c, int(g("days")) if g("days").isdigit() else None, int(g("project_id") or 0))
            m = re.fullmatch(r"/api/journey/timeline/(\d+)", path)
            if m: return journey.timeline(c, int(m.group(1)))
            raise ApiError(404, "Not found")
        # ---- donor care: lapse and regular-giving promises
        if path.startswith("/api/care/"):
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            if path == "/api/care/lapse": return donorcare.lapse(c)
            if path == "/api/care/promises": return donorcare.board(c)
            if path == "/api/care/followup" and method == "POST":
                did = int(self.body().get("donor_id") or 0)
                if not c.execute("SELECT 1 FROM donors WHERE id=?", (did,)).fetchone(): raise ApiError(404, "Donor not found")
                d = logic.asof_date(c).isoformat(); c.execute("UPDATE donors SET next_followup=? WHERE id=?", (d, did)); audit(c, user, "update", "donors", did, dict(next_followup=d)); return {"ok": True}
            raise ApiError(404, "Not found")
        # ---- duplicates
        if path.startswith("/api/dedupe/"):
            kind = g("kind") if method == "GET" else None
            if path == "/api/dedupe/scan" and method == "GET":
                if not (fin if kind == "donors" else prog): raise ApiError(403, "Not allowed")
                return dedupe.scan(c, kind)
            if path == "/api/dedupe/merge" and method == "POST":
                b = self.body(); kind = b.get("kind")
                if not (fin if kind == "donors" else prog): raise ApiError(403, "Not allowed")
                return dedupe.merge(c, user, kind, b.get("keep"), b.get("drop"))
            raise ApiError(404, "Not found")
        # ---- weekly manager summary
        if path.startswith("/api/weekly"):
            if not fin: raise ApiError(403, "Ask an administrator or the accounts officer")
            if path == "/api/weekly" and method == "GET": return weekly.summary(c)
            if path == "/api/weekly/send" and method == "POST":
                if not admin: raise ApiError(403, "Administrators only")
                return weekly.send(c, force=True)
            raise ApiError(404, "Not found")
        # ---- funder / CSR report
        if path == "/api/csr" and method == "GET":
            if not (fin or prog): raise ApiError(403, "Not allowed")
            data, name = csr.report(c, int(g("project_id") or 0), g("from"), g("to"), g("notes")[:1500])
            audit(c, user, "export", "csr_report", int(g("project_id") or 0), dict(a=g("from"), b=g("to")))
            return data, "text/html; charset=utf-8", name
        # ---- searchable audit trail (administrators only)
        if path.startswith("/api/auditlog"):
            if not admin: raise ApiError(403, "Administrators only")
            where, P = ["1=1"], {}
            for k, col in (("user", "user"), ("action", "action"), ("tbl", "tbl")):
                if g(k): where.append(f"{col}=:{k}"); P[k] = g(k)
            if g("row_id").isdigit(): where.append("row_id=:rid"); P["rid"] = int(g("row_id"))
            if g("from"): where.append("ts>=:f"); P["f"] = g("from")
            if g("to"): where.append("ts<:t"); P["t"] = (datetime.date.fromisoformat(g("to")) + datetime.timedelta(days=1)).isoformat() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", g("to")) else g("to")
            if g("q"): where.append("(detail LIKE :q OR tbl LIKE :q OR action LIKE :q OR user LIKE :q)"); P["q"] = "%" + g("q").replace("%", "") + "%"
            W = " AND ".join(where)
            if path == "/api/auditlog/export.csv":
                out = io.StringIO(); w = csv.writer(out); w.writerow(["When", "Who", "Action", "Register", "Record id", "Details"])
                for r in c.execute(f"SELECT * FROM audit WHERE {W} ORDER BY id DESC LIMIT 50000", P): w.writerow([r["ts"], r["user"], r["action"], r["tbl"], r["row_id"], (r["detail"] or "").replace(chr(10), " ")])
                audit(c, user, "export", "audit", None, {k: v for k, v in P.items()})
                return ("\ufeff" + out.getvalue()).encode("utf-8"), "text/csv; charset=utf-8", f"audit-log-{datetime.date.today()}.csv"
            if path == "/api/auditlog":
                lim = min(200, max(10, int(g("limit") or 50))); off = max(0, int(g("offset") or 0))
                total = c.execute(f"SELECT COUNT(*) FROM audit WHERE {W}", P).fetchone()[0]
                rows = [dict(r) for r in c.execute(f"SELECT * FROM audit WHERE {W} ORDER BY id DESC LIMIT {lim} OFFSET {off}", P)]
                fac = dict(users=[r[0] for r in c.execute("SELECT DISTINCT user FROM audit WHERE user IS NOT NULL ORDER BY user")], actions=[r[0] for r in c.execute("SELECT DISTINCT action FROM audit ORDER BY action")],
                           tables=[r[0] for r in c.execute("SELECT DISTINCT tbl FROM audit WHERE tbl IS NOT NULL ORDER BY tbl")])
                return dict(total=total, rows=rows, facets=fac, limit=lim, offset=off)
        raise ApiError(404, "Not found")

    def claims_route(self, c, method, path, q, user):
        parts = path.strip("/").split("/")
        if len(parts) == 2:
            if method == "GET": return claims.listing(c, user, q)
            if method == "POST":
                r = claims.create(c, user, self.body())
                if not r.get("duplicate"): audit(c, user, "create", "claims", r["id"], r)
                return r
        elif parts[2].isdigit():
            cid = int(parts[2])
            if len(parts) == 4 and method == "POST" and parts[3] == "review":
                r = claims.review(c, user, cid, self.body()); audit(c, user, "update", "claims", cid, r); return r
            if len(parts) == 4 and method == "POST" and parts[3] == "pay":
                r = claims.pay(c, user, cid, self.body()); audit(c, user, "update", "claims", cid, r); return r
            if len(parts) == 3 and method == "DELETE":
                files = claims.delete(c, user, cid); audit(c, user, "delete", "claims", cid, {}); c.commit(); media.remove_files(*files); return dict(ok=True)
        raise ApiError(404, "Not found")

    def _drain(self):
        n = int(self.headers.get("Content-Length") or 0)
        while n > 0:
            b = self.rfile.read(min(n, 262144))
            if not b: break
            n -= len(b)

    # --- routing
    def route(self, c, method, path, q):
        # public: login
        if path == "/api/login" and method == "POST":
            b = self.body(); uname = (b.get("username") or "").strip().lower()
            key = (self.ip(), uname)
            tries = [t for t in _fails.get(key, []) if time.time() - t < 300]
            if len(tries) >= 5: raise ApiError(429, "Too many attempts. Wait 5 minutes.")
            r = c.execute("SELECT * FROM users WHERE lower(username)=? AND active=1", (uname,)).fetchone()
            ok = r and secrets.compare_digest(db.hash_pw(b.get("password") or "", r["salt"])[0], r["pw_hash"])
            if not ok:
                tries.append(time.time()); _fails[key] = tries
                audit(c, dict(username=uname[:30] or "?"), "login_failed", "users", r["id"] if r else None, dict(ip=self.ip())); c.commit()
                raise ApiError(401, "Wrong username or password")
            _fails.pop(key, None)
            if r["totp_secret"]:           # password was right; now ask for the 6-digit code
                pre = secrets.token_urlsafe(24); now = time.time()
                for k in [k for k, v in _pre.items() if v["exp"] < now]: _pre.pop(k, None)
                _pre[pre] = dict(uid=r["id"], exp=now + 300, tries=0)
                return {"need_2fa": True, "pre": pre}
            tok = self.start_session(c, r["id"]); audit(c, r, "login", "users", r["id"], dict(ip=self.ip()))
            return {"ok": True, "__cookie": self.cookie(tok)}
        if path == "/api/login/2fa" and method == "POST":
            b = self.body(); pre = _pre.get(b.get("pre") or "")
            if not pre or pre["exp"] < time.time(): raise ApiError(401, "That sign-in timed out. Enter your password again.")
            pre["tries"] += 1
            if pre["tries"] > 5: _pre.pop(b.get("pre"), None); raise ApiError(429, "Too many wrong codes. Sign in again.")
            r = c.execute("SELECT * FROM users WHERE id=? AND active=1", (pre["uid"],)).fetchone()
            if not r or not r["totp_secret"]: raise ApiError(401, "Sign in again")
            code = str(b.get("code") or ""); sec_ = vault.unseal(r["totp_secret"])
            step = vault.check_code(sec_, code, r["totp_last"] or 0)
            if step: c.execute("UPDATE users SET totp_last=? WHERE id=?", (step, r["id"]))
            else:
                left = vault.use_backup(r["backup_codes"], code)
                if left is None:
                    audit(c, r, "login_failed", "users", r["id"], dict(ip=self.ip(), why="2-step code")); c.commit()
                    raise ApiError(401, "That code is not right. Use the current 6 digits from your authenticator app, or a backup code.")
                c.execute("UPDATE users SET backup_codes=? WHERE id=?", (left, r["id"]))
            _pre.pop(b.get("pre"), None)
            tok = self.start_session(c, r["id"]); audit(c, r, "login", "users", r["id"], dict(ip=self.ip(), two_step=True))
            return {"ok": True, "__cookie": self.cookie(tok)}
        # public branding (login page, donate page)
        if path == "/api/public/brand" and method == "GET":
            st = db.get_settings(c)
            return dict(version=VERSION, product=st.get("brand_product") or "NGO Suite", color=st.get("brand_color") or "#0f5e63", note=st.get("login_note", ""), org=st.get("org_name", ""),
                        logo=("/api/public/logo?v=" + st["brand_logo_ver"]) if st.get("brand_logo_ver") else "")
        if path == "/api/public/logo" and method == "GET":
            lg = comms.get_logo(c)
            if not lg: raise ApiError(404, "Not found")
            return lg[0], lg[1], "logo"
        # public donate page (no login)
        if path == "/api/public/donate-info" and method == "GET":
            return automation.public_info(c)
        if path == "/api/public/pledge" and method == "POST":
            try: return automation.public_pledge(c, self.body(), self.client_address[0])
            except ValueError as e: raise ApiError(400, str(e))
            except PermissionError as e: raise ApiError(429, str(e))
        if path == "/api/public/upi.svg" and method == "GET":
            inf = automation.public_info(c)
            if not inf["enabled"]: raise ApiError(404, "Not found")
            return qr.make_svg(inf["link"]).encode(), "image/svg+xml", "upi.svg"
        if path.startswith("/api/hook/"):
            return self.hook_route(c, method, path, q)
        m = re.fullmatch(r"/api/public/card/([A-Za-z0-9_\-]{10,40})", path)
        if m and method == "GET":
            try: return cards.public(c, m.group(1))
            except cards.CardError as e: raise ApiError(e.status, e.msg)
        m = re.fullmatch(r"/api/public/card/([A-Za-z0-9_\-]{10,40})/photo/(\d+)", path)
        if m and method == "GET":
            try: fp, mime, name = cards.public_photo(c, m.group(1), int(m.group(2)))
            except cards.CardError as e: raise ApiError(e.status, e.msg)
            return FileResp(fp, mime, name)
        m = re.fullmatch(r"/api/public/partner/([A-Za-z0-9_\-]{10,40})", path)
        if m and method == "GET":
            try: return partners.portal_page(c, m.group(1)), "text/html; charset=utf-8", "partner.html"
            except partners.PartnerError as e: raise ApiError(e.status, e.msg)
        m = re.fullmatch(r"/api/public/donor/([A-Za-z0-9_\-]{10,40})", path)
        if m and method == "GET":
            try: return v10.donor_page(c, m.group(1)), "text/html; charset=utf-8", "your-giving.html"
            except (v10.V10Error, v14.V14Error) as e: raise ApiError(e.status, e.msg)
        if path == "/api/public/transparency" and method == "GET":
            try: return v10.transparency_page(c), "text/html; charset=utf-8", "transparency.html"
            except v10.V10Error as e: raise ApiError(e.status, e.msg)
        if path == "/api/public/outcomes" and method == "GET":
            return v10.public_outcomes(c)
        user = self.user(c)
        if path == "/api/me": return {"user": self.pub(user)} if user else {"user": None}
        if not user: raise ApiError(401, "Please sign in")
        admin = user["role"] == "admin"
        fin = user["role"] in ("admin", "accountant")
        if path == "/api/logout" and method == "POST":
            m = re.search(r"ngo_session=([A-Za-z0-9_\-]+)", self.headers.get("Cookie") or "")
            c.execute("DELETE FROM sessions WHERE token=?", (m.group(1),))
            return {"ok": True, "__cookie": self.cookie()}
        if path == "/api/logout-all" and method == "POST":
            c.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],)); audit(c, user, "logout_all", "users", user["id"], {})
            return {"ok": True, "__cookie": self.cookie()}
        if path == "/api/password" and method == "POST":
            b = self.body()
            r = c.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
            if not secrets.compare_digest(db.hash_pw(b.get("old") or "", r["salt"])[0], r["pw_hash"]): raise ApiError(400, "Current password is wrong")
            new = b.get("new") or ""
            if len(new) < 8: raise ApiError(400, "New password must be at least 8 characters")
            h, salt = db.hash_pw(new)
            c.execute("UPDATE users SET pw_hash=?, salt=?, must_change=0 WHERE id=?", (h, salt, user["id"]))
            c.execute("DELETE FROM sessions WHERE user_id=? AND token<>?", (user["id"], self.token()))   # other phones/computers must sign in again
            audit(c, user, "password_changed", "users", user["id"], {})
            return {"ok": True}
        if user["must_change"] and path not in ("/api/meta",):
            raise ApiError(403, "Please change your password first")
        if user["need2fa"] and path not in ("/api/meta", "/api/2fa", "/api/2fa/setup", "/api/2fa/enable"):
            raise ApiError(403, "Set up two-step sign-in first")

        # ---- two-step sign-in management (every user, for their own account)
        if path == "/api/2fa" and method == "GET":
            left = len(json.loads(user.get("backup_codes") or "[]"))
            return dict(enabled=user["totp"], backup_left=left, required=user["need2fa"] or (user["role"] == "admin" and db.get_settings(c).get("require_2fa_admin") == "Yes"))
        if path == "/api/2fa/setup" and method == "POST":
            if user["totp"]: raise ApiError(400, "Two-step sign-in is already on")
            sec_ = vault.new_secret(); c.execute("UPDATE users SET totp_pending=? WHERE id=?", (vault.seal(sec_), user["id"]))
            issuer = db.get_settings(c).get("brand_product") or "NGO Suite"
            return dict(secret=sec_, uri=vault.otpauth(sec_, user["username"], issuer), qr=qr.make_svg(vault.otpauth(sec_, user["username"], issuer), 200))
        if path == "/api/2fa/enable" and method == "POST":
            r = c.execute("SELECT totp_pending, totp_secret FROM users WHERE id=?", (user["id"],)).fetchone()
            if r["totp_secret"]: raise ApiError(400, "Two-step sign-in is already on")
            if not r["totp_pending"]: raise ApiError(400, "Start the setup first")
            sec_ = vault.unseal(r["totp_pending"]); step = vault.check_code(sec_, self.body().get("code"))
            if not step: raise ApiError(400, "That code is not right. Check the phone's clock and try the next code.")
            codes, hashed = vault.new_backup_codes()
            c.execute("UPDATE users SET totp_secret=?, totp_pending=NULL, totp_last=?, backup_codes=? WHERE id=?", (vault.seal(sec_), step, hashed, user["id"]))
            c.execute("DELETE FROM sessions WHERE user_id=? AND token<>?", (user["id"], self.token()))
            audit(c, user, "2fa_enabled", "users", user["id"], {})
            return dict(ok=True, codes=codes)
        if path == "/api/2fa/disable" and method == "POST":
            b = self.body(); r = c.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
            if not r["totp_secret"]: raise ApiError(400, "Two-step sign-in is not on")
            if user["role"] == "admin" and db.get_settings(c).get("require_2fa_admin") == "Yes": raise ApiError(400, "Administrators must keep two-step sign-in on (a setting your organisation chose)")
            if not secrets.compare_digest(db.hash_pw(b.get("password") or "", r["salt"])[0], r["pw_hash"]): raise ApiError(400, "Password is wrong")
            if not vault.check_code(vault.unseal(r["totp_secret"]), b.get("code"), r["totp_last"] or 0) and vault.use_backup(r["backup_codes"], b.get("code")) is None: raise ApiError(400, "That code is not right")
            c.execute("UPDATE users SET totp_secret=NULL, totp_pending=NULL, backup_codes=NULL, totp_last=0 WHERE id=?", (user["id"],))
            audit(c, user, "2fa_disabled", "users", user["id"], {})
            return {"ok": True}

        # ---- photos and videos
        if path == "/api/media" or path.startswith("/api/media/"):
            try: return self.media_route(c, method, path, q, user)
            except media.MediaError as e: raise ApiError(e.status, e.msg)

        if path.startswith("/api/inbox"):
            if user["role"] not in ("admin", "accountant"): raise ApiError(403, "Ask an administrator or the accounts officer")
            try: return self.inbox_route(c, method, path, q, user)
            except inbox.InboxError as e: raise ApiError(e.status, e.msg)
        if path.startswith("/api/cards") or path.startswith("/api/pack"):
            if user["role"] not in ("admin", "accountant") and not (path == "/api/cards/preview" and user["role"] == "programme"):
                raise ApiError(403, "Ask an administrator or the accounts officer")
            try: return self.pack_route(c, method, path, q, user)
            except (cards.CardError, compliance_pack.PackError) as e: raise ApiError(e.status, e.msg)
        if re.fullmatch(r"/api/donors/\d+/portal", path) or path.startswith("/api/yearcheck") or path == "/api/policies/starter" or path.startswith("/api/social/") or path.startswith("/api/yearplan") or path.startswith("/api/odocs") or path == "/api/proposal" or path == "/api/notifications":
            try: return self.v10_route(c, method, path, q, user)
            except (v10.V10Error, v14.V14Error) as e: raise ApiError(e.status, e.msg)
        if path.startswith(("/api/partners", "/api/forecast", "/api/relations", "/api/funders", "/api/board")):
            try: return self.v9_route(c, method, path, q, user)
            except partners.PartnerError as e: raise ApiError(e.status, e.msg)
        if path.startswith(("/api/backup/", "/api/journey/", "/api/care/", "/api/dedupe/", "/api/weekly", "/api/csr", "/api/auditlog")):
            try: return self.v8_route(c, method, path, q, user)
            except (securebackup.BackupError, journey.JourneyError, dedupe.DedupeError, csr.CsrError) as e: raise ApiError(e.status, e.msg)
            except ValueError as e: raise ApiError(400, str(e))
        if path == "/api/claims" or path.startswith("/api/claims/"):
            try: return self.claims_route(c, method, path, q, user)
            except claims.ClaimError as e: raise ApiError(e.status, e.msg)

        if path == "/api/meta":
            lists = {}
            for r in c.execute("SELECT kind, value FROM lists ORDER BY id"): lists.setdefault(r["kind"], []).append(r["value"])
            st = db.get_settings(c)
            for k in db.SECRET_KEYS: st[k + "_set"] = "Yes" if st.get(k) else "No"; st[k] = ""
            return dict(gateway=gateway.status(db.get_settings(c)), tables=meta(), lists=lists, user=self.pub(user), roles=ROLE_LABEL, settings=st,
                        formats=[dict(r) for r in c.execute("SELECT * FROM doc_formats ORDER BY sort")])
        if path == "/api/dashboard": return logic.dashboard(c)

        m = re.fullmatch(r"/api/options/(\w+)", path)
        if m and m.group(1) in REF_LABEL: return options(c, m.group(1))

        m = re.fullmatch(r"/api/t/(\w+)(?:/(\d+))?", path)
        if m and m.group(1) in TABLES:
            name, rid = m.group(1), m.group(2)
            spec = TABLES[name]
            if method == "GET" and user["role"] not in spec["read"]: raise ApiError(403, "Your role cannot view this register")
            if method == "GET":
                res = get_row(c, name, int(rid)) if rid else list_rows(c, name, q)
                if name == "team" and user["role"] not in ("admin", "accountant"):
                    for r in ([res] if rid else res): r.pop("bank_account", None); r.pop("ifsc", None)
                if name == "compliance" and rid: res.update(logic.compliance_status(res, logic.asof_date(c)))
                return res
            if user["role"] not in spec["write"]: raise ApiError(403, "Your role cannot change this register")
            if method == "POST" and not rid:
                nid = create(c, name, self.body(), user)
                if name == "donations": c.commit(); automation.auto_receipt_async(nid)
                return get_row(c, name, nid)
            if method == "PUT" and rid:
                update(c, name, int(rid), self.body(), user); return get_row(c, name, int(rid))
            if method == "DELETE" and rid:
                delete(c, name, int(rid), user); return {"ok": True}
            raise ApiError(405, "Method not allowed")

        m = re.fullmatch(r"/api/export/(\w+)\.csv", path)
        if m and m.group(1) in TABLES: return export_csv(c, m.group(1)).encode("utf-8-sig"), "text/csv; charset=utf-8", m.group(1) + ".csv"
        m = re.fullmatch(r"/api/import-template/(\w+)\.csv", path)
        if m and m.group(1) in TABLES:
            sp = TABLES[m.group(1)]
            if user["role"] not in sp["write"]: raise ApiError(403, "Your role cannot change this register")
            buf = io.StringIO(); w = csv.writer(buf); w.writerow([f["l"] for f in sp["fields"]]); return buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", m.group(1) + "-template.csv"
        m = re.fullmatch(r"/api/import/(\w+)", path)
        if m and m.group(1) in TABLES and method == "POST":
            if user["role"] not in TABLES[m.group(1)]["write"]: raise ApiError(403, "Your role cannot change this register")
            b = self.body(); return import_csv(c, m.group(1), b.get("csv", ""), user, dry=bool(b.get("dry")))

        if path.startswith("/api/report/"):
            r = path[len("/api/report/"):]
            ym = (q.get("month") or [""])[0] or logic.asof(db.get_settings(c)).strftime("%Y-%m")
            if not re.fullmatch(r"\d{4}-\d{2}", ym): raise ApiError(400, "Month must look like 2026-04")
            pid = int((q.get("project_id") or ["0"])[0] or 0)
            if r == "donors": return logic.donor_dashboard(c)
            if r == "projects": return logic.project_dashboard(c)
            if r == "payroll": return logic.payroll(c, ym)
            if r == "grants": return {"grants": logic.grants_list(c)}
            if r == "funds": return logic.fund_dashboard(c)
            if r == "trustee": return logic.trustee_report(c, ym)
            if r == "budget": return logic.budget_tools(c, pid or None)
            if r == "impact":
                gift = (q.get("gift") or [""])[0]
                res = logic.impact_report(c, pid, (q.get("donor") or [""])[0], float(gift) if gift else None)
                if not res: raise ApiError(404, "Pick a project")
                return res
            if r == "all_projects": return logic.all_projects(c)
            raise ApiError(404, "Unknown report")

        m = re.fullmatch(r"/api/print/(?!payslip)(\w+)/(\d+)", path)
        if m:
            kind, i = m.group(1), int(m.group(2))
            fn = dict(receipt=logic.print_receipt, statement=logic.print_donor_statement, voucher=logic.print_voucher,
                      utilisation=logic.print_utilisation, activity=logic.print_activity).get(kind)
            res = fn(c, i) if fn else (logic.print_record(c, i, (q.get("format") or [""])[0]) if kind == "record" else None)
            if not res: raise ApiError(404, "Nothing to print")
            return res

        # ---- birthdays and email
        if path == "/api/birthdays" and method == "GET":
            days = max(0, min(int((q.get("days") or ["30"])[0] or 30), 366))
            people = logic.birthday_people(c, days)
            yr = logic.asof_date(c).year
            return dict(people=people, sent_this_year=c.execute("SELECT COUNT(*) FROM email_log WHERE kind='birthday' AND status='sent' AND year=?", (yr,)).fetchone()[0],
                        email_ready=bool(db.get_settings(c).get("smtp_host")), auto=db.get_settings(c).get("birthday_auto") == "Yes")
        if path == "/api/birthdays/send" and method == "POST":
            if user["role"] not in ("admin", "accountant"): raise ApiError(403, "Not allowed")
            b = self.body()
            if b.get("tbl") not in ("donors", "team"): raise ApiError(400, "Pick a donor or team member")
            p = next((x for x in logic.birthday_people(c, 366) if x["tbl"] == b["tbl"] and x["id"] == int(b.get("id") or 0)), None)
            if not p: raise ApiError(404, "No birthday found for that person")
            r = mailer.send_wish(c, p)
            if r["status"] == "failed": c.commit(); raise ApiError(502, r["reason"])
            return r
        if path == "/api/birthdays/run" and method == "POST":
            if user["role"] not in ("admin", "accountant"): raise ApiError(403, "Not allowed")
            return mailer.run_today(c, respect_failures=False)
        if path == "/api/email/test" and method == "POST":
            if not admin: raise ApiError(403, "Administrators only")
            s = db.get_settings(c)
            try: mailer.send_mail(s, (self.body().get("to") or "").strip(), "Test email from " + s.get("org_name", "NGO Suite"), "This is a test. Your email settings work.")
            except mailer.MailError as e: raise ApiError(502, str(e))
            return {"ok": True}
        if path == "/api/email-log" and method == "GET":
            if user["role"] not in ("admin", "accountant"): raise ApiError(403, "Not allowed")
            return [dict(r) for r in c.execute("SELECT * FROM email_log ORDER BY id DESC LIMIT 100")]

        # ---- branding, follow-ups, communication
        if path == "/api/branding/logo" and method == "POST":
            if not admin: raise ApiError(403, "Administrators only")
            try: return dict(ok=True, ver=comms.save_logo(c, self.body().get("data")))
            except ValueError as e: raise ApiError(400, str(e))
        if path == "/api/branding/logo" and method == "DELETE":
            if not admin: raise ApiError(403, "Administrators only")
            comms.remove_logo(c); return {"ok": True}
        if path == "/api/followups" and method == "GET": return comms.followups(c)
        m = re.fullmatch(r"/api/donors/(\d+)/timeline", path)
        if m:
            r = comms.timeline(c, int(m.group(1)))
            if not r: raise ApiError(404, "Not found")
            return r
        if path == "/api/campaign/segments" and method == "GET":
            return dict(segments=[dict(key=k, label=l, param=p) for k, l, p in comms.SEGMENTS], cities=[r[0] for r in c.execute("SELECT DISTINCT city FROM donors WHERE COALESCE(city,'')<>'' ORDER BY city")],
                        groups=comms.groups(c), languages=langpack.LANGS, gateway=gateway.status(db.get_settings(c)), email=bool(db.get_settings(c).get("smtp_host")))
        m = re.fullmatch(r"/api/campaign/(\d+)(?:/(retry|cancel))?", path)
        if m:
            if not fin: raise ApiError(403, "Not allowed")
            cid, act = int(m.group(1)), m.group(2)
            try:
                if not act and method == "GET":
                    r = comms.campaign_detail(c, cid)
                    if not r: raise ApiError(404, "Not found")
                    return r
                if act == "retry" and method == "POST": c.commit(); comms.retry_failed(c, cid); return {"ok": True}
                if act == "cancel" and method == "POST": comms.cancel(c, cid); audit(c, user, "update", "campaigns", cid, dict(status="Cancelled")); return {"ok": True}
            except ValueError as e: raise ApiError(400, str(e))
        if path == "/api/gateway/test" and method == "POST":
            if not admin: raise ApiError(403, "Administrators only")
            b = self.body()
            try: return comms.test_gateway(c, str(b.get("channel") or ""), str(b.get("to") or ""), b.get("template") or "", b.get("variables") or "")
            except ValueError as e: raise ApiError(400, str(e))
        if path == "/api/campaigns" and method == "GET":
            if not fin: raise ApiError(403, "Not allowed")
            return [dict(r) for r in c.execute("SELECT id,ts,name,channel,segment,subject,total,sent,failed,status,user FROM campaigns ORDER BY id DESC LIMIT 50")]
        if path in ("/api/campaign/preview", "/api/campaign/send", "/api/campaign/whatsapp") and method == "POST":
            if not fin: raise ApiError(403, "Not allowed")
            b = self.body()
            try:
                if path.endswith("preview"): return comms.preview(c, b.get("segment"), str(b.get("param") or ""))
                if path.endswith("whatsapp"): return dict(list=comms.whatsapp_list(c, b.get("segment"), str(b.get("param") or ""), (b.get("body") or "")[:2000]))
                cid, n, _t, sched = comms.start_campaign(c, user, b.get("name"), b.get("segment"), str(b.get("param") or ""), b.get("subject"), b.get("body"),
                                                         str(b.get("channel") or "email").lower(), b.get("template") or "", b.get("variables") or "", b.get("schedule_at") or "")
                audit(c, user, "create", "campaigns", cid, dict(name=b.get("name"), channel=b.get("channel"), total=n)); return dict(id=cid, total=n, scheduled=sched)
            except ValueError as e: raise ApiError(400, str(e))

        # ---- automation endpoints
        m = re.fullmatch(r"/api/donations/(\d+)/email", path)
        if m and method == "POST":
            if not fin: raise ApiError(403, "Not allowed")
            try: return automation.receipt_email(c, int(m.group(1)), force=bool(self.body().get("force")))
            except mailer.MailError as e: raise ApiError(502, str(e))
        if path == "/api/automation/status" and method == "GET":
            if not fin: raise ApiError(403, "Not allowed")
            st = db.get_settings(c)
            return dict(email_ready=bool(st.get("smtp_host")), last_backup=st.get("last_backup", ""), digest=automation.digest(c), deadlines=automation.deadline_triggers(c))
        m = re.fullmatch(r"/api/automation/run/(digest|deadlines|trustee|impact|backup)", path)
        if m and method == "POST":
            if user["role"] != "admin": raise ApiError(403, "Administrators only")
            k = m.group(1)
            if k == "backup": return automation.run_backup(c)
            if not db.get_settings(c).get("smtp_host"): raise ApiError(400, "Set up email in Settings first")
            fn = dict(digest=lambda: automation.send_digest(c), deadlines=lambda: automation.send_deadline_alerts(c), trustee=lambda: automation.send_trustee_report(c), impact=lambda: automation.send_impact_reports(c))[k]
            return fn()
        m = re.fullmatch(r"/api/compliance/(\d+)/done", path)
        if m and method == "POST":
            if not fin: raise ApiError(403, "Not allowed")
            row = c.execute("SELECT * FROM compliance WHERE id=?", (int(m.group(1)),)).fetchone()
            if not row: raise ApiError(404, "Not found")
            today = logic.asof_date(c).isoformat()
            c.execute("UPDATE compliance SET last_done=? WHERE id=?", (today, row["id"])); audit(c, user, "update", "compliance", row["id"], dict(last_done=today))
            return get_row(c, "compliance", row["id"]) | logic.compliance_status(dict(c.execute("SELECT * FROM compliance WHERE id=?", (row["id"],)).fetchone()), logic.asof_date(c))
        if path == "/api/bank/preview" and method == "POST":
            if not fin: raise ApiError(403, "Not allowed")
            try: return automation.bank_preview(c, self.body().get("csv", ""))
            except ValueError as e: raise ApiError(400, str(e))
        if path == "/api/bank/commit" and method == "POST":
            if not fin: raise ApiError(403, "Not allowed")
            b = self.body(); fid = int(b.get("fund_id") or 0) or None
            if fid and not c.execute("SELECT 1 FROM funds WHERE id=?", (fid,)).fetchone(): raise ApiError(400, "Choose a valid fund")
            return automation.bank_commit(c, b.get("items") or [], fid, user, create, update)
        m = re.fullmatch(r"/api/print/payslip/(\d+)", path)
        if m:
            if not fin: raise ApiError(403, "Not allowed")
            ym = (q.get("month") or [""])[0] or logic.asof(db.get_settings(c)).strftime("%Y-%m")
            if not re.fullmatch(r"\d{4}-\d{2}", ym): raise ApiError(400, "Month must look like 2026-04")
            r = automation.payslip(c, int(m.group(1)), ym)
            if not r: raise ApiError(404, "Nothing to print")
            return r
        if path == "/api/export/payroll-bank.csv":
            if not fin: raise ApiError(403, "Not allowed")
            ym = (q.get("month") or [""])[0] or logic.asof(db.get_settings(c)).strftime("%Y-%m")
            if not re.fullmatch(r"\d{4}-\d{2}", ym): raise ApiError(400, "Month must look like 2026-04")
            return automation.bank_sheet(c, ym).encode("utf-8-sig"), "text/csv; charset=utf-8", f"salary-bank-{ym}.csv"
        if path == "/api/qr.svg":
            t = (q.get("text") or [""])[0]
            if not t or len(t) > 200: raise ApiError(400, "Text is required (max 200 characters)")
            return qr.make_svg(t).encode(), "image/svg+xml", "qr.svg"
        m = re.fullmatch(r"/api/pledges/(\d+)/convert", path)
        if m and method == "POST":
            if not fin: raise ApiError(403, "Not allowed")
            return automation.convert_pledge(c, int(m.group(1)), user, create)
        if path == "/api/attendance/mark" and method == "POST":
            if user["role"] not in TABLES["attendance"]["write"]: raise ApiError(403, "Your role cannot change this register")
            b = self.body(); tid = int(b.get("team_id") or 0); d = (b.get("date") or "")[:10] or logic.asof_date(c).isoformat()
            st = b.get("attendance") or "P"
            if st not in ("P", "A", "H", "L"): raise ApiError(400, "Attendance must be P, A, H or L")
            ex = c.execute("SELECT id FROM attendance WHERE team_id=? AND date=?", (tid, d)).fetchone()
            if ex: update(c, "attendance", ex["id"], dict(attendance=st), user)
            else: create(c, "attendance", dict(team_id=tid, date=d, attendance=st), user)
            return {"ok": True, "date": d}
        if path == "/api/duplicates" and method == "GET":
            return automation.find_duplicates(c, (q.get("phone") or [""])[0], (q.get("name") or [""])[0], (q.get("village") or [""])[0])
        if path == "/api/field/activity" and method == "POST":
            if user["role"] not in ("admin", "programme"): raise ApiError(403, "Your role cannot log activities")
            b = self.body(); cid = (str(b.pop("client_id", "") or ""))[:60]
            if cid:
                old = c.execute("SELECT id FROM activities WHERE client_id=?", (cid,)).fetchone()
                if old: return dict(id=old["id"], duplicate=True)
            rid = create(c, "activities", b, user)
            if cid: c.execute("UPDATE activities SET client_id=? WHERE id=?", (cid, rid))
            return dict(id=rid)
        if path == "/api/field/team" and method == "GET":
            d = logic.asof_date(c).isoformat()
            return dict(date=d, team=[dict(r) for r in c.execute("SELECT t.id, t.code, t.name, t.role, (SELECT attendance FROM attendance a WHERE a.team_id=t.id AND a.date=?) att FROM team t WHERE t.active='Y' AND t.pay_type<>'Volunteer' ORDER BY t.name", (d,))])

        # ---- admin area
        if path == "/api/settings" and method == "PUT":
            if not admin: raise ApiError(403, "Administrators only")
            b = self.body()
            for k, v in b.items():
                if k not in db.DEFAULT_SETTINGS: raise ApiError(400, f"Unknown setting {k}")
                if k == "last_backup" or k == "brand_logo_ver": continue
                if k == "brand_color":
                    if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(v)): raise ApiError(400, "Colour must look like #0f5e63")
                    if comms.lum(v) > 0.25: raise ApiError(400, "That colour is too light for white text. Pick a darker one.")
                if k == "brand_product" and not 1 <= len(str(v).strip()) <= 40: raise ApiError(400, "Software name must be 1 to 40 characters")
                if k == "login_note" and len(str(v)) > 160: raise ApiError(400, "Login line is too long (160 characters)")
                lim = dict(digest_hour=23, report_day=28, backup_keep=365).get(k)
                if lim and (not str(v).isdigit() or not (1 if k != "digest_hour" else 0) <= int(v) <= lim): raise ApiError(400, f"{k.replace('_', ' ')} must be a whole number up to {lim}")
                if k == "backup_password" and v and len(str(v)) < securebackup.MIN_PW: raise ApiError(400, f"Use a backup password of at least {securebackup.MIN_PW} characters")
                if k in ("commit_remind_days", "stale_journey_days") and (not str(v).isdigit() or not 1 <= int(v) <= 365): raise ApiError(400, f"{k.replace('_', ' ')} must be a whole number from 1 to 365")
                if k in ("core_monthly_cost", "major_donor_min", "reserve_months"):
                    try: ok = 0 <= float(v) <= 1e10
                    except ValueError: ok = False
                    if not ok: raise ApiError(400, f"{k.replace('_', ' ')} must be a number, 0 or more")
                if k == "lapse_factor":
                    try: ok = 1.1 <= float(v) <= 10
                    except ValueError: ok = False
                    if not ok: raise ApiError(400, "Lapse factor must be a number between 1.1 and 10")
                if k == "weekly_wa_to" and v and not all(re.fullmatch(r"\+?[0-9]{10,14}", x) for x in re.split(r"[,;\s]+", v) if x): raise ApiError(400, "WhatsApp numbers look wrong (digits only, with country code if outside India)")
                if k in ("digest_to", "trustee_emails", "weekly_to") and v and not all(EMAIL_RE.match(x) for x in re.split(r"[,;\s]+", v) if x): raise ApiError(400, "One of those email addresses looks wrong")
                if k in db.SECRET_KEYS and v == "": continue   # blank = keep the saved secret
                if k in ("wa_provider", "sms_provider") and v not in gateway.PROVIDERS["whatsapp" if k == "wa_provider" else "sms"]: raise ApiError(400, "Pick a provider from the list")
                if k == "custom_url" and v and not str(v).lower().startswith("https://"): raise ApiError(400, "Provider address must start with https://")
                if k == "custom_headers" and v:
                    try:
                        if not isinstance(json.loads(v), dict): raise ValueError
                    except ValueError: raise ApiError(400, 'Custom headers must be JSON like {"Authorization": "Bearer …"}')
                if k == "birthday_send_hour" and not str(v).isdigit() or k == "birthday_send_hour" and int(v) > 23: raise ApiError(400, "Send hour must be 0 to 23")
                if k == "smtp_port" and not str(v).isdigit(): raise ApiError(400, "Mail port must be a number")
                if k == "smtp_security" and v not in ("starttls", "ssl", "none"): raise ApiError(400, "Pick starttls, ssl or none")
                if k == "asof_override" and v:
                    try: datetime.date.fromisoformat(v)
                    except ValueError: raise ApiError(400, "As-on date must look like 2026-11-13")
                c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, vault.seal(str(v)) if k in db.SECRET_KEYS else str(v)))
            st = db.get_settings(c)
            for k in db.SECRET_KEYS: st[k + "_set"] = "Yes" if st.get(k) else "No"; st[k] = ""
            return st
        if path == "/api/tool-settings" and method == "PUT":  # planning inputs: finance roles may change
            if user["role"] not in ("admin", "accountant"): raise ApiError(403, "Not allowed")
            for k, v in self.body().items():
                if k not in db.DEFAULT_SETTINGS or k.startswith(("smtp_", "birthday_", "org_", "digest_", "trustee_", "backup_", "donate_", "auto_", "last_", "deadline_", "impact_", "brand_", "login_", "setup_", "wa_", "sms_", "twilio_", "custom_", "weekly_", "commit_", "backup", "public_", "transparency_", "outcome_", "ca_", "auditor_")) or k == "asof_override":
                    raise ApiError(400, f"Setting {k} cannot be changed here")
                c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, str(v)))
            return {"ok": True}
        if path == "/api/formats" and method == "PUT":
            if not admin: raise ApiError(403, "Administrators only")
            b = self.body(); 
            c.execute("UPDATE doc_formats SET title=?,line1=?,line2=?,line3=?,show_lines=?,show_amounts=?,sign_left=?,sign_right=? WHERE name=?",
                      (b.get("title"), b.get("line1"), b.get("line2"), b.get("line3"), b.get("show_lines", "Y"), b.get("show_amounts", "Y"), b.get("sign_left"), b.get("sign_right"), b.get("name")))
            return {"ok": True}
        if path == "/api/lists":
            if method == "POST":
                if user["role"] == "viewer": raise ApiError(403, "Not allowed")
                b = self.body(); v = (b.get("value") or "").strip()
                if not v or b.get("kind") not in db.DEFAULT_LISTS: raise ApiError(400, "Pick a list and type a value")
                c.execute("INSERT OR IGNORE INTO lists(kind,value) VALUES(?,?)", (b["kind"], v)); return {"ok": True}
        m = re.fullmatch(r"/api/lists/(\d+)", path)
        if m and method == "DELETE":
            if not admin: raise ApiError(403, "Administrators only")
            c.execute("DELETE FROM lists WHERE id=?", (int(m.group(1)),)); return {"ok": True}
        if path == "/api/lists/all" and method == "GET":
            return [dict(r) for r in c.execute("SELECT * FROM lists ORDER BY kind, id")]
        if path == "/api/users":
            if not admin: raise ApiError(403, "Administrators only")
            if method == "GET": return [self.pub(dict(r)) | {"active": r["active"]} for r in c.execute("SELECT * FROM users ORDER BY username")]
            if method == "POST":
                b = self.body(); un = (b.get("username") or "").strip().lower()
                if not re.fullmatch(r"[a-z0-9_.\-]{3,30}", un): raise ApiError(400, "Username: 3-30 letters, digits, . _ -")
                if b.get("role") not in ROLES: raise ApiError(400, "Pick a role")
                if len(b.get("password") or "") < 8: raise ApiError(400, "Password must be at least 8 characters")
                h, salt = db.hash_pw(b["password"])
                try: c.execute("INSERT INTO users(username,name,role,pw_hash,salt,must_change) VALUES(?,?,?,?,?,1)", (un, b.get("name") or un, b["role"], h, salt))
                except sqlite3.IntegrityError: raise ApiError(400, "That username is taken")
                return {"ok": True}
        m = re.fullmatch(r"/api/users/(\d+)", path)
        if m and method == "PUT":
            if not admin: raise ApiError(403, "Administrators only")
            uid = int(m.group(1)); b = self.body()
            if uid == user["id"] and (b.get("active") == 0 or b.get("role", "admin") != "admin"): raise ApiError(400, "You cannot lock yourself out")
            if "role" in b:
                if b["role"] not in ROLES: raise ApiError(400, "Pick a role")
                c.execute("UPDATE users SET role=? WHERE id=?", (b["role"], uid))
            if "active" in b:
                c.execute("UPDATE users SET active=? WHERE id=?", (1 if b["active"] else 0, uid))
                if not b["active"]: c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            if b.get("password"):
                if len(b["password"]) < 8: raise ApiError(400, "Password must be at least 8 characters")
                h, salt = db.hash_pw(b["password"]); c.execute("UPDATE users SET pw_hash=?, salt=?, must_change=1 WHERE id=?", (h, salt, uid))
                c.execute("DELETE FROM sessions WHERE user_id=?", (uid,)); audit(c, user, "password_reset", "users", uid, {})
            return {"ok": True}
        m2 = re.fullmatch(r"/api/users/(\d+)/reset2fa", path)
        if m2 and method == "POST":
            if not admin: raise ApiError(403, "Administrators only")
            uid = int(m2.group(1))
            c.execute("UPDATE users SET totp_secret=NULL, totp_pending=NULL, backup_codes=NULL, totp_last=0 WHERE id=?", (uid,))
            c.execute("DELETE FROM sessions WHERE user_id=? AND ?<>?", (uid, uid, user["id"]))
            audit(c, user, "2fa_reset", "users", uid, {})
            return {"ok": True}
        if path == "/api/audit":
            if not admin: raise ApiError(403, "Administrators only")
            return [dict(r) for r in c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 300")]
        if path == "/api/backup":
            if not admin: raise ApiError(403, "Administrators only")
            tmp = os.path.join(tempfile.mkdtemp(), "backup.db")
            dst = sqlite3.connect(tmp); c.backup(dst); dst.close()
            with open(tmp, "rb") as fh: data = fh.read()
            shutil.rmtree(os.path.dirname(tmp))
            return data, "application/octet-stream", f"ngo-backup-{datetime.date.today()}.db"
        raise ApiError(404, "Unknown endpoint")

    @staticmethod
    def pub(u):
        return dict(id=u["id"], username=u["username"], name=u["name"], role=u["role"], must_change=u["must_change"], totp=bool(u.get("totp_secret")), need2fa=bool(u.get("need2fa")))

def serve(host="127.0.0.1", port=8000):
    db.init_db()
    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd
