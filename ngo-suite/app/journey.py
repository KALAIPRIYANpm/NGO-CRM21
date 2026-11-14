"""Beneficiary journey: one timeline per person (enrolled, assessed, service, follow-up, outcome) and a project funnel."""
import datetime
from . import logic, db

ORDER = ["Enrolled", "Assessed", "Service started", "Service given", "Follow-up visit", "Milestone reached", "Outcome achieved"]
END = ("Exited", "Dropped out")

class JourneyError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg); self.status, self.msg = status, msg

def timeline(c, bid):
    b = logic.one(c, "SELECT b.*, p.name project FROM beneficiaries b LEFT JOIN projects p ON p.id=b.project_id WHERE b.id=:i", dict(i=bid))
    if not b: raise JourneyError(404, "Person not found")
    ev = logic.rows(c, "SELECT id, date, stage, detail, outcome, recorded_by FROM journey WHERE beneficiary_id=:i ORDER BY date, id", dict(i=bid))
    if not any(e["stage"] == "Enrolled" for e in ev) and b.get("date_joined"):
        ev.insert(0, dict(id=0, date=b["date_joined"], stage="Enrolled", detail="Joined " + (b["project"] or "the project") + (", service: " + b["service"] if b.get("service") else ""), outcome="", recorded_by="", implied=True))
    ev.sort(key=lambda e: (e["date"] or "", e["id"]))
    today = logic.asof_date(c)
    last = ev[-1]["date"] if ev else None
    quiet = (today - datetime.date.fromisoformat(last)).days if last else None
    reached = {e["stage"] for e in ev}
    nxt = next((s for s in ORDER if s not in reached), None)
    closed = next((e["stage"] for e in reversed(ev) if e["stage"] in END), None)
    return dict(person=b, events=ev, days_quiet=quiet, next_step=None if closed else nxt, closed=closed, achieved="Outcome achieved" in reached)

def summary(c, project_id=0):
    where, p = ("WHERE b.project_id=:p", dict(p=project_id)) if project_id else ("", {})
    people = logic.rows(c, f"SELECT b.id, b.status FROM beneficiaries b {where}", p)
    ids = {r["id"] for r in people}
    ev = logic.rows(c, f"SELECT j.beneficiary_id bid, j.stage, j.date FROM journey j JOIN beneficiaries b ON b.id=j.beneficiary_id {where}", p)
    by = {}
    for e in ev: by.setdefault(e["bid"], set()).add(e["stage"])
    funnel = []
    for st in ORDER:
        n = len(ids) if st == "Enrolled" else sum(1 for i in ids if st in by.get(i, set()))
        funnel.append(dict(stage=st, count=n))
    ended = sum(1 for i in ids if by.get(i, set()) & set(END))
    outcomes = logic.rows(c, f"SELECT j.outcome, COUNT(*) n FROM journey j JOIN beneficiaries b ON b.id=j.beneficiary_id {where} {'AND' if where else 'WHERE'} j.stage='Outcome achieved' AND COALESCE(j.outcome,'')<>'' GROUP BY j.outcome ORDER BY n DESC LIMIT 10", p)
    return dict(total=len(ids), funnel=funnel, exited=ended, outcomes=outcomes)

def stale(c, days=None, project_id=0):
    s, today, _ = logic.ctx(c)
    days = int(days if days is not None else db.num(s, "stale_journey_days", 45))
    cut = (today - datetime.timedelta(days=days)).isoformat()
    sql = """SELECT b.id, b.code, b.name, b.phone, b.village, p.name project,
             COALESCE((SELECT MAX(date) FROM journey WHERE beneficiary_id=b.id), b.date_joined) last_seen
             FROM beneficiaries b LEFT JOIN projects p ON p.id=b.project_id
             WHERE b.status='Active' AND NOT EXISTS (SELECT 1 FROM journey j WHERE j.beneficiary_id=b.id AND j.stage IN ('Exited','Dropped out'))"""
    p = {}
    if project_id: sql += " AND b.project_id=:p"; p["p"] = project_id
    out = [r for r in logic.rows(c, sql, p) if (r["last_seen"] or "0000") < cut]
    for r in out:
        r["days_quiet"] = (today - datetime.date.fromisoformat(r["last_seen"])).days if r["last_seen"] else None
    out.sort(key=lambda r: -(r["days_quiet"] or 99999))
    return dict(days=days, people=out[:200], count=len(out))

def people_list(c, q="", project_id=0):
    sql = """SELECT b.id, b.code, b.name, b.village, p.name project, b.status,
             (SELECT COUNT(*) FROM journey j WHERE j.beneficiary_id=b.id) steps,
             (SELECT stage FROM journey j WHERE j.beneficiary_id=b.id ORDER BY date DESC, id DESC LIMIT 1) last_stage
             FROM beneficiaries b LEFT JOIN projects p ON p.id=b.project_id WHERE 1=1"""
    P = {}
    if q: sql += " AND (b.name LIKE :q OR b.code LIKE :q OR b.village LIKE :q)"; P["q"] = f"%{q}%"
    if project_id: sql += " AND b.project_id=:p"; P["p"] = project_id
    return logic.rows(c, sql + " ORDER BY b.name LIMIT 100", P)
