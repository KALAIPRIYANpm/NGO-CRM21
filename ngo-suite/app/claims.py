"""Expense claims from the field: staff photograph the bill, finance approves, then pays and the
payment posts to the Cash Book. The person who made the claim can never approve or pay it."""
import re, datetime
from . import media

class ClaimError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg); self.status, self.msg = status, msg

def _money(v):
    try: x = round(float(str(v).replace(",", "")), 2)
    except ValueError: raise ClaimError(400, "Amount is not a number")
    if x <= 0 or x > 10_000_000: raise ClaimError(400, "Amount must be more than zero")
    return x

def _code(c):
    mx = 0
    for (v,) in c.execute("SELECT claim_no FROM claims"):
        m = re.fullmatch(r"EC-(\d+)", v or "")
        if m: mx = max(mx, int(m.group(1)))
    return f"EC-{mx + 1:04d}"

def listing(c, user, q):
    where, args = ["1=1"], []
    if user["role"] == "viewer": raise ClaimError(403, "Not allowed")
    if user["role"] == "programme": where.append("c.user_id=?"); args.append(user["id"])
    st = q.get("status", [""])[0]
    if st: where.append("c.status=?"); args.append(st)
    rows = c.execute(f"""SELECT c.*, p.name project, (SELECT COUNT(*) FROM media m WHERE m.claim_id=c.id) bills
        FROM claims c LEFT JOIN projects p ON p.id=c.project_id WHERE {' AND '.join(where)} ORDER BY c.id DESC LIMIT 300""", args).fetchall()
    return [dict(r) for r in rows]

def create(c, user, b):
    if user["role"] not in ("admin", "programme"): raise ClaimError(403, "Your role cannot file claims")
    cid = (str(b.get("client_id") or ""))[:60]
    if cid:
        old = c.execute("SELECT id, claim_no FROM claims WHERE client_id=?", (cid,)).fetchone()
        if old: return dict(id=old["id"], claim_no=old["claim_no"], duplicate=True)
    date = str(b.get("date") or datetime.date.today().isoformat())[:10]
    try: datetime.date.fromisoformat(date)
    except ValueError: raise ClaimError(400, "Date is not valid")
    if date > (datetime.date.today() + datetime.timedelta(days=1)).isoformat(): raise ClaimError(400, "Date is in the future")
    pid = b.get("project_id") or None
    if pid and not c.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone(): raise ClaimError(400, "Project not found")
    amt = _money(b.get("amount"))
    no = _code(c)
    cur = c.execute("INSERT INTO claims(claim_no,date,user_id,claimant,project_id,category,amount,description,status,client_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (no, date, user["id"], user.get("name") or user["username"], pid, (b.get("category") or "Other")[:60], amt,
                     (b.get("description") or "")[:500], "Pending", cid or None))
    return dict(id=cur.lastrowid, claim_no=no)

def review(c, user, cid, b):
    if user["role"] not in ("admin", "accountant"): raise ClaimError(403, "Only finance can approve or reject claims")
    r = c.execute("SELECT * FROM claims WHERE id=?", (cid,)).fetchone()
    if not r: raise ClaimError(404, "Claim not found")
    if r["user_id"] == user["id"]: raise ClaimError(403, "You cannot approve your own claim. Ask another finance user.")
    if r["status"] != "Pending": raise ClaimError(400, f"This claim is already {r['status']}")
    act = b.get("action")
    if act not in ("approve", "reject"): raise ClaimError(400, "Choose approve or reject")
    remark = (b.get("remark") or "")[:300]
    if act == "reject" and not remark: raise ClaimError(400, "Please write a reason for rejecting")
    c.execute("UPDATE claims SET status=?, reviewed_by=?, reviewed_on=?, remark=? WHERE id=?",
              ("Approved" if act == "approve" else "Rejected", user.get("name") or user["username"], datetime.date.today().isoformat(), remark, cid))
    return dict(status="Approved" if act == "approve" else "Rejected")

def pay(c, user, cid, b):
    if user["role"] not in ("admin", "accountant"): raise ClaimError(403, "Only finance can pay claims")
    r = c.execute("SELECT * FROM claims WHERE id=?", (cid,)).fetchone()
    if not r: raise ClaimError(404, "Claim not found")
    if r["user_id"] == user["id"]: raise ClaimError(403, "You cannot pay your own claim. Ask another finance user.")
    if r["status"] != "Approved": raise ClaimError(400, "Only an approved claim can be paid")
    f = c.execute("SELECT id FROM funds WHERE id=?", (b.get("fund_id"),)).fetchone()
    if not f: raise ClaimError(400, "Choose the fund this is paid from")
    day = str(b.get("paid_on") or datetime.date.today().isoformat())[:10]
    try: datetime.date.fromisoformat(day)
    except ValueError: raise ClaimError(400, "Date is not valid")
    mx = 100
    for (v,) in c.execute("SELECT voucher_no FROM cash_book WHERE voucher_no LIKE 'PM-%'"):
        m = re.fullmatch(r"PM-(\d+)", v or "")
        if m: mx = max(mx, int(m.group(1)))
    cur = c.execute("INSERT INTO cash_book(date,voucher_no,type,fund_id,head,party,mode,amount,note,source) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (day, f"PM-{mx + 1}", "Payment", f["id"], r["category"] or "Other", r["claimant"], (b.get("mode") or "Cash")[:30], r["amount"],
                     f"Expense claim {r['claim_no']}", f"claims:{cid}"))
    c.execute("UPDATE claims SET status='Paid', paid_on=?, cash_book_id=? WHERE id=?", (day, cur.lastrowid, cid))
    return dict(status="Paid", voucher_no=f"PM-{mx + 1}")

def delete(c, user, cid):
    r = c.execute("SELECT * FROM claims WHERE id=?", (cid,)).fetchone()
    if not r: raise ClaimError(404, "Claim not found")
    if user["role"] != "admin" and not (r["user_id"] == user["id"] and r["status"] == "Pending"):
        raise ClaimError(403, "You can only withdraw your own claim while it is still pending")
    if r["status"] in ("Paid", "Approved"): raise ClaimError(400, f"A claim that is {r['status']} cannot be deleted")
    files = []
    for m in c.execute("SELECT file, thumb FROM media WHERE claim_id=?", (cid,)): files += [m["file"], m["thumb"]]
    c.execute("DELETE FROM media WHERE claim_id=?", (cid,)); c.execute("DELETE FROM claims WHERE id=?", (cid,))
    return files
