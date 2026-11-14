"""v14.1: one notification list (the bell): what is coming up or overdue, filtered by the person's role."""
import datetime
from . import logic

def build(c, role, days=14):
    s, today, P = logic.ctx(c)
    end = (today + datetime.timedelta(days=days)).isoformat(); a = today.isoformat(); out = []
    fin, prog = role in ("admin", "accountant"), role in ("admin", "accountant", "programme")
    def add(kind, when, text, link, red=False):
        left = (datetime.date.fromisoformat(when) - today).days if when else 0
        out.append(dict(kind=kind, date=when, days=left, text=text, link=link, level="red" if (red or left < 0 or left <= 2) else "amber"))
    if prog:
        for b in logic.birthday_people(c, days):
            who = f"{b['name']} ({b['kind'].lower()})" + (f", turning {b['turning']}" if b.get("turning") else "")
            add("Birthday", b["next_date"], who + (" today" if b["days_away"] == 0 else ""), "#/r/birthdays", red=b["days_away"] == 0)
        for r in logic.rows(c, "SELECT title, date, kind FROM plan_calendar WHERE date>=? AND date<=? AND status IN ('Idea','Planned')", (a, end)):
            add("Festival or campaign", r["date"], f"{r['title']}: not yet confirmed", "#/t/plan_calendar")
    for r in logic.rows(c, "SELECT title, date, venue FROM partner_events WHERE date>=? AND date<=? AND status NOT IN ('Done','Cancelled')", (a, end)):
        add("Event", r["date"], r["title"] + (f" at {r['venue']}" if r["venue"] else ""), "#/t/partner_events")
    for r in logic.rows(c, "SELECT name, start, end, stage FROM projects WHERE stage<>'Closed'"):
        if r["end"] and r["end"] < a: add("Programme", r["end"], f"{r['name']}: end date has passed", "#/r/projects", red=True)
        elif r["end"] and r["end"] <= end: add("Programme", r["end"], f"{r['name']} ends", "#/r/projects")
        if r["start"] and a <= r["start"] <= end: add("Programme", r["start"], f"{r['name']} starts", "#/r/projects")
    if fin:
        for x in logic.compliance_list(c):
            if x["cstatus"] in ("Overdue", "Due soon") and x.get("due_date"): add("Compliance", x["due_date"], x["title"] + (": overdue" if x["cstatus"] == "Overdue" else ""), "#/t/compliance")
        for r in logic.rows(c, "SELECT name, valid_until FROM official_docs WHERE status='Have' AND COALESCE(valid_until,'')<>'' AND valid_until<=?", (( today + datetime.timedelta(days=60)).isoformat(),)):
            add("Document", r["valid_until"], r["name"] + (" has expired" if r["valid_until"] < a else " expires"), "#/t/official_docs")
        for x in logic.dashboard(c)["alerts"]:
            if x.get("link") == "grants": out.append(dict(kind="Grant", date="", days=0, text=x["text"], link="#/r/grants", level=x["level"]))
        for r in logic.rows(c, "SELECT date, kind, next_date FROM meetings WHERE COALESCE(next_date,'')<>'' AND next_date>=? AND next_date<=?", (a, end)):
            add("Meeting", r["next_date"], f"Next {r['kind'] or 'meeting'} planned", "#/t/meetings")
        for r in logic.rows(c, "SELECT company, next_step, next_date, decision_by FROM csr_pipeline WHERE stage NOT IN ('Declined','Closed')"):
            if r["next_date"] and r["next_date"] <= end: add("Company", r["next_date"], f"{r['company']}: {r['next_step'] or 'next step'}", "#/t/csr_pipeline")
            if r["decision_by"] and a <= r["decision_by"] <= end: add("Company", r["decision_by"], f"{r['company']}: decision expected", "#/t/csr_pipeline")
        n = c.execute("SELECT COUNT(*) FROM donors WHERE COALESCE(next_followup,'')<>'' AND next_followup<=?", (a,)).fetchone()[0]
        if n: out.append(dict(kind="Donor follow-up", date=a, days=0, text=f"{n} donor call{'s' if n != 1 else ''} due", link="#/r/followups", level="amber"))
    out.sort(key=lambda x: (x["date"] or "0000", x["kind"]))
    return dict(items=out, count=len(out), red=sum(1 for i in out if i["level"] == "red"), days=days)
