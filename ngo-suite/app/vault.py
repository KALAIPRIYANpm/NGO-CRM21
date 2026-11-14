"""Security helpers (standard library only): encryption of stored secrets, and two-step sign-in codes.

Encryption: provider keys (WhatsApp/SMS tokens, mail password) are stored encrypted, so a copied database
file or backup does not reveal them. The key lives in  data/secret.key  (or env NGO_SECRET_KEY), kept
separate from the database. Construction: HMAC-SHA256 in counter mode as a stream cipher, with an
HMAC-SHA256 tag over nonce+ciphertext (encrypt-then-MAC). It is a modest, reviewable construction built from
standard primitives, not AES. It protects the database file; it does not protect against someone who can
read both the database and the key file on the server.
"""
import os, hmac, hashlib, base64, secrets, struct, time, json
from urllib.parse import quote
from . import db

PREFIX = "enc1:"
_key = None

def _key_path():
    return os.path.join(os.path.dirname(os.path.abspath(db.DB_PATH)), "secret.key")

def master():
    global _key
    if _key: return _key
    env = os.environ.get("NGO_SECRET_KEY")
    if env:
        _key = hashlib.sha256(env.encode()).digest(); return _key
    p = _key_path()
    if os.path.exists(p):
        with open(p) as fh: _key = base64.b64decode(fh.read().strip())
    else:
        k = secrets.token_bytes(32)
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as fh: fh.write(base64.b64encode(k).decode())
            _key = k
        except FileExistsError:
            with open(p) as fh: _key = base64.b64decode(fh.read().strip())
    return _key

def _sub(label): return hmac.new(master(), label, hashlib.sha256).digest()

def _stream(nonce, n):
    k, out, i = _sub(b"enc"), b"", 0
    while len(out) < n:
        out += hmac.new(k, nonce + struct.pack(">Q", i), hashlib.sha256).digest(); i += 1
    return out[:n]

def seal(text):
    if not text or str(text).startswith(PREFIX): return text
    pt = str(text).encode(); nonce = secrets.token_bytes(16)
    ct = bytes(a ^ b for a, b in zip(pt, _stream(nonce, len(pt))))
    tag = hmac.new(_sub(b"mac"), nonce + ct, hashlib.sha256).digest()[:16]
    return PREFIX + base64.urlsafe_b64encode(nonce + ct + tag).decode()

def unseal(text):
    """Plain text passes through (older databases). A value that cannot be verified comes back empty."""
    if not text or not str(text).startswith(PREFIX): return text
    try:
        raw = base64.urlsafe_b64decode(text[len(PREFIX):]); nonce, ct, tag = raw[:16], raw[16:-16], raw[-16:]
        if not hmac.compare_digest(hmac.new(_sub(b"mac"), nonce + ct, hashlib.sha256).digest()[:16], tag): return ""
        return bytes(a ^ b for a, b in zip(ct, _stream(nonce, len(ct)))).decode()
    except Exception:
        return ""

def migrate(c):
    """Encrypt any provider secret that is still stored as plain text."""
    n = 0
    for k in db.SECRET_KEYS:
        r = c.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
        if r and r["value"] and not r["value"].startswith(PREFIX):
            c.execute("UPDATE settings SET value=? WHERE key=?", (seal(r["value"]), k)); n += 1
    return n

# ------------------------------------------------------------------ two-step sign-in (RFC 6238 TOTP)
def new_secret(): return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")

def _hotp(secret, counter, digits=6):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest(); o = h[-1] & 15
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 10 ** digits).zfill(digits)

def totp_now(secret, t=None, digits=6): return _hotp(secret, int((time.time() if t is None else t) // 30), digits)

def check_code(secret, code, last=0, t=None):
    """Return the accepted time-step (so it can be recorded and never reused) or None."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != 6: return None
    now = int((time.time() if t is None else t) // 30)
    for off in (0, -1, 1):
        step = now + off
        if step > (last or 0) and hmac.compare_digest(_hotp(secret, step), code): return step
    return None

def otpauth(secret, account, issuer):
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"

def _norm(code): return "".join(ch for ch in str(code or "").lower() if ch.isalnum())
def new_backup_codes(n=8):
    codes = [secrets.token_hex(2) + "-" + secrets.token_hex(2) for _ in range(n)]
    return codes, json.dumps([hashlib.sha256(_norm(x).encode()).hexdigest() for x in codes])
def use_backup(stored_json, code):
    """Return the remaining list (json) if the code was valid, else None. Each code works once."""
    try: hs = json.loads(stored_json or "[]")
    except ValueError: return None
    h = hashlib.sha256(_norm(code).encode()).hexdigest()
    for x in hs:
        if hmac.compare_digest(x, h): hs.remove(x); return json.dumps(hs)
    return None
