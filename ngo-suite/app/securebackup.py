"""Password-protected backups and restore (standard library only).

File format (.ngobk):  magic line + JSON header (salt, iterations, created) + ciphertext + 16-byte tag.
Key: PBKDF2-HMAC-SHA256 from your backup password, split into an encryption key and a MAC key.
Cipher: HMAC-SHA256 in counter mode with an encrypt-then-MAC tag (the same modest construction as vault.py, not AES).
Inside is a zip with the database and the server key file, so a restore on a new computer also brings back saved
mail and WhatsApp credentials. Photos and videos (data/media) are NOT inside; copy that folder separately.
Keep the password somewhere safe: without it the file cannot be opened, and nobody can recover it for you."""
import os, io, json, hmac, hashlib, secrets, struct, sqlite3, tempfile, zipfile, datetime, shutil, base64
from . import db, vault

MAGIC = b"NGOBK1\n"
ITER = 200_000
MIN_PW = 8

class BackupError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg); self.status, self.msg = status, msg

def _keys(pw, salt, iters):
    k = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, iters, 64)
    return k[:32], k[32:]

def _stream(key, nonce, n):
    out, i = bytearray(), 0
    while len(out) < n:
        out += hmac.new(key, nonce + struct.pack(">Q", i), hashlib.sha256).digest(); i += 1
    return bytes(out[:n])

def _xor(a, b):
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(len(a), "big") if a else b""

def check_password(pw):
    if not pw or len(pw) < MIN_PW: raise BackupError(400, f"Use a backup password of at least {MIN_PW} characters")

def encrypt(data, pw, iters=ITER):
    check_password(pw)
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(16)
    ek, mk = _keys(pw, salt, iters)
    ct = _xor(data, _stream(ek, nonce, len(data)))
    head = json.dumps(dict(v=1, salt=base64.b64encode(salt).decode(), nonce=base64.b64encode(nonce).decode(), iters=iters,
                           created=datetime.datetime.now().isoformat(timespec="seconds"), size=len(ct))).encode()
    body = MAGIC + head + b"\n" + ct
    return body + hmac.new(mk, body, hashlib.sha256).digest()[:16]

def decrypt(blob, pw):
    if not blob.startswith(MAGIC): raise BackupError(400, "This is not a password-protected backup from this software")
    try:
        rest = blob[len(MAGIC):]; nl = rest.index(b"\n"); head = json.loads(rest[:nl])
        salt, nonce, iters = base64.b64decode(head["salt"]), base64.b64decode(head["nonce"]), int(head["iters"])
        if not 1000 <= iters <= 5_000_000: raise ValueError
        ct = rest[nl + 1:-16]; tag = blob[-16:]
    except (ValueError, KeyError, TypeError):
        raise BackupError(400, "This backup file is damaged")
    ek, mk = _keys(pw or "", salt, iters)
    if not hmac.compare_digest(hmac.new(mk, blob[:-16], hashlib.sha256).digest()[:16], tag):
        raise BackupError(400, "Wrong password, or the file is damaged")
    return _xor(ct, _stream(ek, nonce, len(ct)))

def _db_bytes(c):
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "x.db"); dst = sqlite3.connect(p); c.backup(dst); dst.close()
        with open(p, "rb") as fh: return fh.read()
    finally: shutil.rmtree(d, ignore_errors=True)

def make(c, pw):
    """Encrypted backup of the whole database, as bytes."""
    check_password(pw)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("ngo.db", _db_bytes(c))
        z.writestr("secret.key", base64.b64encode(vault.master()).decode())
        z.writestr("about.txt", "NGO Suite backup made " + datetime.datetime.now().isoformat(timespec="seconds") + ". Photos and videos are not included.")
    return encrypt(buf.getvalue(), pw)

def _validate(path):
    try:
        t = sqlite3.connect(path)
        try:
            if t.execute("PRAGMA integrity_check").fetchone()[0] != "ok": raise BackupError(400, "The backup database is damaged")
            have = {r[0] for r in t.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally: t.close()
    except sqlite3.DatabaseError:
        raise BackupError(400, "That file is not a database backup")
    need = {"users", "settings", "donors", "donations"}
    if not need <= have: raise BackupError(400, "That database is not an NGO Suite backup (tables are missing)")

def _unseal_with(key, text):
    """Decrypt a stored secret using the key from the backup (not this computer's key)."""
    if not text or not str(text).startswith(vault.PREFIX): return text
    old = vault._key
    try:
        vault._key = key
        return vault.unseal(text)
    finally: vault._key = old

def restore(c, blob, pw, user_name="admin"):
    """Replace the live data with a backup (password-protected .ngobk or a plain .db). Returns a short report.
    A safety copy of the current data is saved first. Everyone is signed out afterwards."""
    c.commit(); old_key = None
    if blob.startswith(MAGIC):
        zf = zipfile.ZipFile(io.BytesIO(decrypt(blob, pw)))
        names = set(zf.namelist())
        if "ngo.db" not in names: raise BackupError(400, "The backup has no database inside")
        raw = zf.read("ngo.db")
        if "secret.key" in names:
            try: old_key = base64.b64decode(zf.read("secret.key").decode().strip())
            except ValueError: old_key = None
    elif blob.startswith(b"SQLite format 3\x00"):
        raw = blob
    else:
        raise BackupError(400, "Choose a backup file ending in .ngobk or .db")
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "restore.db")
        with open(p, "wb") as fh: fh.write(raw)
        _validate(p)
        # settings secrets were sealed with the key of the computer that made the backup; re-seal for this one
        t = sqlite3.connect(p)
        try:
            for k in db.SECRET_KEYS:
                r = t.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
                if r and r[0] and str(r[0]).startswith(vault.PREFIX):
                    plain = _unseal_with(old_key, r[0]) if old_key else ""
                    t.execute("UPDATE settings SET value=? WHERE key=?", (vault.seal(plain) if plain else "", k))
            t.commit()
        finally: t.close()
        keep = os.path.join(os.path.dirname(os.path.abspath(db.DB_PATH)), "backups"); os.makedirs(keep, exist_ok=True)
        safety = os.path.join(keep, "before-restore-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".db")
        sd = sqlite3.connect(safety); c.backup(sd); sd.close()
        src = sqlite3.connect(p)
        try: src.backup(c)
        finally: src.close()
        c.commit()
    finally: shutil.rmtree(d, ignore_errors=True)
    db.init_db()                      # bring an older backup up to this version
    c2 = db.connect()
    try:
        c2.execute("DELETE FROM sessions"); c2.commit()
        n = {t: c2.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("donors", "donations", "beneficiaries")}
    finally: c2.close()
    return dict(ok=True, safety_copy=os.path.basename(safety), counts=n)

def stamp(): return datetime.date.today().isoformat()
