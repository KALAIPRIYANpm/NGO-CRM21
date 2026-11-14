"""Donor-ready impact cards: one page per project per month, built from the field's own records.
A card is a frozen snapshot behind a private, unguessable link that can be revoked. Only photos where
everyone shown agreed (consent = Y) can appear, and a photo disappears if that consent is later withdrawn."""
import json, secrets, datetime, calendar
from . import logic, db, media

class CardError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg); self.status, self.msg = status, msg

def _month(m):
    try: y, mo = (int(x) for x in str(m).split("-")); datetime.date(y, mo, 1)
    except (ValueError, TypeError): raise CardError(400, "Month must look like 2026-10")
    return f"{y:04d}-{mo:02d}", f"{y:04d}-{mo:02d}-01", f"{y:04d}-{mo:02d}-{calendar.monthrange(y, mo)[1]:02d}"

def _label(m): return datetime.date(int(m[:4]), int(m[5:7]), 1).strftime("%B %Y")

def build(c, project_id, month):
    p = logic.one(c, "SELECT * FROM projects WHERE id=:i", dict(i=project_id))
    if not p: raise CardError(404, "Project not found")
    month, a, b = _month(month)
    t = logic.one(c, """SELECT COUNT(*) activities, COALESCE(SUM(people_reached),0) people, COALESCE(SUM(volunteers),0) volunteers, COALESCE(SUM(spent),0) spent
                        FROM activities WHERE project_id=:p AND date BETWEEN :a AND :b""", dict(p=project_id, a=a, b=b))
    villages = [r["village"] for r in c.execute("SELECT DISTINCT village FROM activities WHERE project_id=? AND date BETWEEN ? AND ? AND COALESCE(village,'')<>'' ORDER BY village", (project_id, a, b))]
    kinds = [r["activity"] for r in c.execute("SELECT activity, COUNT(*) n FROM activities WHERE project_id=? AND date BETWEEN ? AND ? AND COALESCE(activity,'')<>'' GROUP BY activity ORDER BY n DESC LIMIT 4", (project_id, a, b))]
    photos = logic.rows(c, """SELECT id, caption, taken_at, created FROM media WHERE project_id=:p AND purpose='event' AND kind='photo' AND consent='Y'
                              AND substr(COALESCE(NULLIF(taken_at,''), created),1,10) BETWEEN :a AND :b ORDER BY id DESC LIMIT 24""", dict(p=project_id, a=a, b=b))
    results = [dict(result=r["result"], unit=r["unit"], target=r["target"], achieved=r["achieved"]) for r in c.execute("SELECT * FROM results WHERE project_id=? ORDER BY id LIMIT 3", (project_id,))]
    people = int(t["people"] or 0)
    return dict(project=p["name"], place=p["place"] or "", month=month, month_label=_label(month), activities=t["activities"], people=people, volunteers=int(t["volunteers"] or 0),
                spent=round(t["spent"] or 0, 2), per_person=round(t["spent"] / people, 2) if people else None, villages=villages, kinds=kinds, photos=photos, results=results,
                suggested_headline=(f"{people:,} people reached in {_label(month)}" + (f" in {villages[0]}" if len(villages) == 1 else "")) if people else f"{_label(month)} at {p['name']}")

def create(c, user, b):
    pid = b.get("project_id")
    d = build(c, pid, b.get("month"))
    head = str(b.get("headline") or d["suggested_headline"]).strip()[:120]
    story = str(b.get("story") or "").strip()[:700]
    ids = [int(x) for x in (b.get("photo_ids") or []) if str(x).isdigit()][:4]
    ok = {p["id"] for p in d["photos"]}
    if any(i not in ok for i in ids): raise CardError(400, "A chosen photo is not available (it needs consent and the right project and month)")
    if not d["activities"] and not story: raise CardError(400, "There are no activities logged for that month. Log some, or write a short story.")
    st = db.get_settings(c); o = logic.org_info(st)
    snap = dict(org=o.get("name", ""), color=o["color"], logo=o["logo"], contact=" · ".join(x for x in (o.get("phone"), o.get("email")) if x), project=d["project"], place=d["place"], month=d["month"],
                month_label=d["month_label"], headline=head, story=story, activities=d["activities"], people=d["people"], volunteers=d["volunteers"], spent=d["spent"], per_person=d["per_person"],
                villages=d["villages"], kinds=d["kinds"], results=d["results"], photo_ids=ids, captions={str(p["id"]): p["caption"] or "" for p in d["photos"] if p["id"] in ids})
    tok = secrets.token_urlsafe(16)
    cur = c.execute("INSERT INTO impact_cards(token,project_id,month,data,created,created_by) VALUES(?,?,?,?,?,?)",
                    (tok, pid, d["month"], json.dumps(snap), datetime.datetime.now().isoformat(timespec="seconds"), user.get("name") or user["username"]))
    return dict(id=cur.lastrowid, token=tok, url=f"/card.html?t={tok}")

def listing(c):
    out = []
    for r in c.execute("SELECT c.*, p.name project FROM impact_cards c LEFT JOIN projects p ON p.id=c.project_id ORDER BY c.id DESC LIMIT 100"):
        d = json.loads(r["data"]); out.append(dict(id=r["id"], project=r["project"], month=r["month"], headline=d.get("headline"), created=r["created"], created_by=r["created_by"],
                                                    revoked=r["revoked"], views=r["views"], last_view=r["last_view"], url=f"/card.html?t={r['token']}", photos=len(d.get("photo_ids", []))))
    return out

def revoke(c, cid):
    if not c.execute("SELECT 1 FROM impact_cards WHERE id=?", (cid,)).fetchone(): raise CardError(404, "Card not found")
    c.execute("UPDATE impact_cards SET revoked=1 WHERE id=?", (cid,))

def public(c, token):
    r = c.execute("SELECT * FROM impact_cards WHERE token=? AND revoked=0", (str(token)[:40],)).fetchone()
    if not r: raise CardError(404, "This link is no longer available")
    c.execute("UPDATE impact_cards SET views=views+1, last_view=? WHERE id=?", (datetime.datetime.now().isoformat(timespec="seconds"), r["id"]))
    d = json.loads(r["data"])
    live = {m["id"] for m in c.execute("SELECT id FROM media WHERE consent='Y' AND id IN (%s)" % ",".join("?" * len(d["photo_ids"])), d["photo_ids"])} if d["photo_ids"] else set()
    d["photo_ids"] = [i for i in d["photo_ids"] if i in live]          # a withdrawn consent removes the photo from the card at once
    d["token"] = token
    return d

def public_photo(c, token, mid):
    r = c.execute("SELECT data FROM impact_cards WHERE token=? AND revoked=0", (str(token)[:40],)).fetchone()
    if not r or mid not in json.loads(r["data"]).get("photo_ids", []): raise CardError(404, "Not found")
    m = c.execute("SELECT * FROM media WHERE id=? AND consent='Y' AND kind='photo'", (mid,)).fetchone()
    if not m: raise CardError(404, "Not found")
    return media.abspath(m["file"]), m["mime"], f"photo-{mid}.jpg"
