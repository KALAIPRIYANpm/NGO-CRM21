"""Find people entered twice (donors, people served) and merge them without losing any history."""
import re, json, difflib, datetime
from . import logic

class DedupeError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg); self.status, self.msg = status, msg

def _digits(x): return re.sub(r"\D", "", x or "")[-10:]
def _norm(x):
    x = re.sub(r"\b(mr|mrs|ms|dr|shri|smt|sri|shree|late)\b\.?", " ", (x or "").lower())
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", x).split())

class _UF:
    def __init__(self): self.p = {}
    def f(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x: self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def u(self, a, b): self.p[self.f(a)] = self.f(b)

def scan(c, kind):
    if kind not in ("donors", "beneficiaries"): raise DedupeError(400, "Choose donors or people served")
    if kind == "donors":
        rows = logic.rows(c, """SELECT d.id, d.code, d.name, d.phone, d.email, d.city, d.id_no, d.birthday,
              (SELECT COUNT(*) FROM donations n WHERE n.donor_id=d.id) donations, (SELECT COALESCE(SUM(amount),0) FROM donations n WHERE n.donor_id=d.id) total,
              (SELECT COUNT(*) FROM interactions i WHERE i.donor_id=d.id) notes FROM donors d""")
        place = "city"
    else:
        rows = logic.rows(c, """SELECT b.id, b.code, b.name, b.phone, b.village, b.gender, b.age_group, p.name project,
              (SELECT COUNT(*) FROM journey j WHERE j.beneficiary_id=b.id) steps FROM beneficiaries b LEFT JOIN projects p ON p.id=b.project_id""")
        place = "village"
    uf = _UF(); why = {}
    def link(a, b, reason): uf.u(a["id"], b["id"]); why.setdefault(uf.f(a["id"]), set()).add(reason); why.setdefault(a["id"], set()).add(reason); why.setdefault(b["id"], set()).add(reason)
    by_phone, by_mail, by_name, blocks = {}, {}, {}, {}
    for r in rows:
        ph = _digits(r["phone"])
        if len(ph) >= 10: by_phone.setdefault(ph, []).append(r)
        em = (r.get("email") or "").strip().lower()
        if em: by_mail.setdefault(em, []).append(r)
        n = _norm(r["name"]); r["_n"] = n
        if n: by_name.setdefault((n, (r.get(place) or "").strip().lower()), []).append(r); blocks.setdefault(n[:3], []).append(r)
    for grp, label in ((by_phone, "same phone number"), (by_mail, "same email")):
        for g in grp.values():
            for x in g[1:]: link(g[0], x, label)
    for (n, pl), g in by_name.items():
        if len(g) > 1 and (pl or kind == "donors"):
            for x in g[1:]: link(g[0], x, "same name" + (" and place" if pl else ""))
    for b in blocks.values():        # near-identical spellings in the same place: Ramesh Patil / Rameshh Patil
        if len(b) > 250: continue
        for i, x in enumerate(b):
            for y in b[i + 1:]:
                if x["_n"] == y["_n"] or (x.get(place) or "").strip().lower() != (y.get(place) or "").strip().lower() or not (x.get(place) or "").strip(): continue
                if difflib.SequenceMatcher(None, x["_n"], y["_n"]).ratio() >= 0.9: link(x, y, "very similar name in the same place")
    groups = {}
    for r in rows:
        if r["id"] in uf.p: groups.setdefault(uf.f(r["id"]), []).append(r)
    out = []
    for root, g in groups.items():
        if len(g) < 2: continue
        reasons = sorted({w for r in g for w in why.get(r["id"], ())})
        for r in g: r.pop("_n", None)
        pans = {(r.get("id_no") or "").strip().upper() for r in g if (r.get("id_no") or "").strip()}
        # suggest keeping the record with the most history
        keep = max(g, key=lambda r: (r.get("donations", r.get("steps", 0)), r.get("notes", 0), -r["id"]))["id"]
        out.append(dict(records=sorted(g, key=lambda r: r["id"]), reasons=reasons, suggested_keep=keep, conflict="Different ID/PAN numbers: check before merging" if len(pans) > 1 else ""))
    out.sort(key=lambda x: -len(x["records"]))
    return dict(kind=kind, groups=out[:200], count=len(out))

DONOR_LINKS = [("donations", "donor_id"), ("interactions", "donor_id"), ("commitments", "donor_id"), ("inbox", "donor_id")]
BEN_LINKS = [("journey", "beneficiary_id")]
FILL = {"donors": ["phone", "email", "city", "donor_type", "id_no", "birthday", "language"], "beneficiaries": ["phone", "village", "gender", "age_group", "service"]}

def merge(c, user, kind, keep_id, drop_ids):
    if kind not in ("donors", "beneficiaries"): raise DedupeError(400, "Choose donors or people served")
    try: keep_id = int(keep_id); drop_ids = sorted({int(x) for x in drop_ids or []})
    except (TypeError, ValueError): raise DedupeError(400, "Ids must be numbers")
    if not drop_ids or keep_id in drop_ids: raise DedupeError(400, "Pick one record to keep and at least one other to merge into it")
    if len(drop_ids) > 10: raise DedupeError(400, "Merge at most 10 records at a time")
    keep = c.execute(f"SELECT * FROM {kind} WHERE id=?", (keep_id,)).fetchone()
    if not keep: raise DedupeError(404, "The record to keep was not found")
    keep = dict(keep); dropped = []
    for i in drop_ids:
        r = c.execute(f"SELECT * FROM {kind} WHERE id=?", (i,)).fetchone()
        if not r: raise DedupeError(404, f"Record {i} was not found")
        dropped.append(dict(r))
    if kind == "donors":
        pans = {(r.get("id_no") or "").strip().upper() for r in [keep] + dropped if (r.get("id_no") or "").strip()}
        if len(pans) > 1: raise DedupeError(400, "These donors have different PAN/ID numbers, so they may be different people. Correct one first.")
    moved = {}
    for t, col in (DONOR_LINKS if kind == "donors" else BEN_LINKS):
        for i in drop_ids:
            n = c.execute(f"UPDATE {t} SET {col}=? WHERE {col}=?", (keep_id, i)).rowcount
            if n: moved[t] = moved.get(t, 0) + n
    upd = {}
    for col in FILL[kind]:
        if not (keep.get(col) or "").strip():
            v = next((d.get(col) for d in dropped if (d.get(col) or "").strip()), None)
            if v: upd[col] = v
    if kind == "donors":
        fu = [x for x in [keep.get("next_followup")] + [d.get("next_followup") for d in dropped] if x]
        if fu: upd["next_followup"] = min(fu)
        extra = "\n".join(f"[merged from {d['code']} {d['name']}] {d['notes']}" for d in dropped if (d.get("notes") or "").strip())
        if extra: upd["notes"] = ((keep.get("notes") or "") + "\n" + extra).strip()
    if upd: c.execute(f"UPDATE {kind} SET {','.join(k + '=?' for k in upd)} WHERE id=?", [*upd.values(), keep_id])
    for i in drop_ids: c.execute(f"DELETE FROM {kind} WHERE id=?", (i,))
    c.execute("INSERT INTO audit(ts,user,action,tbl,row_id,detail) VALUES(?,?,?,?,?,?)",
              (datetime.datetime.now().isoformat(timespec="seconds"), user["username"], "merge", kind, keep_id,
               json.dumps(dict(kept=keep.get("code"), merged=[dict(code=d.get("code"), name=d.get("name"), phone=d.get("phone"), email=d.get("email")) for d in dropped], moved=moved), ensure_ascii=False)[:1500]))
    return dict(ok=True, kept=keep.get("code"), merged=len(drop_ids), moved=moved)
