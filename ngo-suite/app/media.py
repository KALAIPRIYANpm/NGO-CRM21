"""Photo and video capture: validation, privacy stripping, storage, listing.

Files live under  <data folder>/media/YYYY/MM/<random>.<ext>  and are only ever served
through the authenticated API (never as plain static files).
"""
import os, secrets, datetime, struct
from . import db

MAX_PHOTO = 8_000_000
MAX_VIDEO = 60_000_000
MAX_THUMB = 400_000
CHUNK = 256 * 1024

class MediaError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg); self.status, self.msg = status, msg

def root():
    return os.path.join(os.path.dirname(os.path.abspath(db.DB_PATH)), "media")

def sniff(head):
    """Return (kind, ext, mime) from the first bytes, or None. The client's Content-Type is never trusted."""
    if head[:3] == b"\xff\xd8\xff": return ("photo", "jpg", "image/jpeg")
    if head[:8] == b"\x89PNG\r\n\x1a\n": return ("photo", "png", "image/png")
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP": return ("photo", "webp", "image/webp")
    if head[4:8] == b"ftyp":
        return ("video", "mov" if head[8:12] == b"qt  " else "mp4", "video/quicktime" if head[8:12] == b"qt  " else "video/mp4")
    if head[:4] == b"\x1a\x45\xdf\xa3": return ("video", "webm", "video/webm")
    return None

def strip_jpeg(data):
    """Remove EXIF/XMP (APP1) and Photoshop/IPTC (APP13) segments: this is where GPS position,
    camera serial number and the photographer's name are stored. Image data is left untouched."""
    if data[:2] != b"\xff\xd8": return data
    out = bytearray(b"\xff\xd8"); i = 2; n = len(data)
    while i + 4 <= n:
        if data[i] != 0xFF: break
        m = data[i + 1]
        if m == 0xFF: i += 1; continue
        if m == 0xDA or m == 0xD9:       # start of scan / end: copy the rest as is
            out += data[i:]; return bytes(out)
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            out += data[i:i + 2]; i += 2; continue
        ln = struct.unpack(">H", data[i + 2:i + 4])[0]
        if ln < 2 or i + 2 + ln > n: break
        if m not in (0xE1, 0xED):
            out += data[i:i + 2 + ln]
        i += 2 + ln
    out += data[i:]
    return bytes(out)

def has_exif(data):
    return data[:2] == b"\xff\xd8" and (b"Exif\x00\x00" in data[:70000] or b"ns.adobe.com/xap" in data[:70000])

def _newpath(ext, suffix=""):
    now = datetime.date.today()
    d = os.path.join(root(), f"{now.year}", f"{now.month:02d}")
    os.makedirs(d, exist_ok=True)
    name = secrets.token_hex(12) + suffix + "." + ext
    return os.path.join(f"{now.year}", f"{now.month:02d}", name).replace("\\", "/"), os.path.join(d, name)

def abspath(rel):
    fp = os.path.normpath(os.path.join(root(), rel))
    if not fp.startswith(os.path.normpath(root()) + os.sep): raise MediaError(400, "Bad file path")
    return fp

def save_stream(rfile, length, want):
    """Read `length` bytes of a request body into a new file. want = 'photo' | 'video' | 'thumb'.
    Reads in chunks, so a 60 MB video never sits in memory. Returns (rel, kind, mime, size)."""
    if length <= 0: raise MediaError(400, "Empty upload")
    limit = {"photo": MAX_PHOTO, "video": MAX_VIDEO, "thumb": MAX_THUMB}[want]
    if length > limit: raise MediaError(413, f"File too large (limit {limit // 1_000_000 if limit >= 1_000_000 else limit // 1000} {'MB' if limit >= 1_000_000 else 'KB'})")
    first = rfile.read(min(CHUNK, length))
    info = sniff(first)
    if not info: raise MediaError(415, "Unsupported file. Use JPEG, PNG or WebP photos and MP4, MOV or WebM videos.")
    kind, ext, mime = info
    if want == "thumb":
        if ext != "jpg": raise MediaError(415, "Thumbnail must be JPEG")
    elif kind != want:
        raise MediaError(415, f"This is not a {want}")
    rel, fp = _newpath(ext, ".t" if want == "thumb" else "")
    got = len(first)
    try:
        with open(fp, "wb") as fh:
            fh.write(first)
            while got < length:
                b = rfile.read(min(CHUNK, length - got))
                if not b: raise MediaError(400, "Upload was cut off. Please try again.")
                fh.write(b); got += len(b)
        if ext == "jpg":
            with open(fp, "rb") as fh: raw = fh.read()
            if has_exif(raw):
                with open(fp, "wb") as fh: fh.write(strip_jpeg(raw))
    except BaseException:
        try: os.remove(fp)
        except OSError: pass
        raise
    return rel, kind, mime, os.path.getsize(fp)

def remove_files(*rels):
    for r in rels:
        if not r: continue
        try: os.remove(abspath(r))
        except (OSError, MediaError): pass

# ------------------------------------------------------------------ records
def can_see(user, row):
    if row["purpose"] == "bill": return user["role"] in ("admin", "accountant", "programme")
    if user["role"] == "viewer": return row["consent"] == "Y"
    return True

def row_json(r):
    d = dict(r)
    d.pop("file", None); d.pop("thumb", None); d["has_thumb"] = bool(r["thumb"])
    return d

def create(c, user, kind, rel, mime, size, q):
    def num(k):
        try: return int(q.get(k, [""])[0]) if q.get(k, [""])[0] else None
        except ValueError: raise MediaError(400, f"Bad {k}")
    pid, aid, cid = num("project_id"), num("activity_id"), num("claim_id")
    if pid and not c.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone(): raise MediaError(400, "Project not found")
    if aid and not c.execute("SELECT 1 FROM activities WHERE id=?", (aid,)).fetchone(): raise MediaError(400, "Activity not found")
    if cid:
        cl = c.execute("SELECT user_id, status FROM claims WHERE id=?", (cid,)).fetchone()
        if not cl: raise MediaError(400, "Claim not found")
        if cl["user_id"] != user["id"] and user["role"] != "admin": raise MediaError(403, "You can only add bills to your own claim")
        if cl["status"] != "Pending": raise MediaError(400, "This claim is no longer pending")
    purpose = "bill" if cid or q.get("purpose", [""])[0] == "bill" else "event"
    consent = "Y" if q.get("consent", ["N"])[0] == "Y" else "N"
    cap = (q.get("caption", [""])[0] or "")[:300]
    taken = (q.get("taken_at", [""])[0] or "")[:25]
    client = (q.get("client_id", [""])[0] or "")[:60]
    cur = c.execute("INSERT INTO media(kind,purpose,file,mime,size,project_id,activity_id,claim_id,caption,consent,taken_at,uploaded_by,uploader,created,client_id) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (kind, purpose, rel, mime, size, pid, aid, cid, cap, consent, taken, user["id"], user.get("name") or user["username"],
                     datetime.datetime.now().isoformat(timespec="seconds"), client or None))
    return cur.lastrowid

def listing(c, user, q):
    where, args = ["1=1"], []
    if user["role"] == "viewer": where.append("m.consent='Y'")
    purpose = q.get("purpose", ["event"])[0]
    if purpose == "bill" and user["role"] == "viewer": raise MediaError(403, "Not allowed")
    where.append("m.purpose=?"); args.append("bill" if purpose == "bill" else "event")
    for k, col in (("project_id", "m.project_id"), ("activity_id", "m.activity_id"), ("claim_id", "m.claim_id"), ("kind", "m.kind"), ("consent", "m.consent")):
        v = q.get(k, [""])[0]
        if v: where.append(f"{col}=?"); args.append(v)
    before = q.get("before", [""])[0]
    if before.isdigit(): where.append("m.id<?"); args.append(int(before))
    try: lim = max(1, min(int(q.get("limit", ["48"])[0]), 100))
    except ValueError: lim = 48
    rows = c.execute(f"SELECT m.*, p.name project FROM media m LEFT JOIN projects p ON p.id=m.project_id WHERE {' AND '.join(where)} ORDER BY m.id DESC LIMIT ?", args + [lim + 1]).fetchall()
    more = len(rows) > lim
    return dict(items=[row_json(r) for r in rows[:lim]], more=more)
