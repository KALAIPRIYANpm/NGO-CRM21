"""v13: yearly plan. Festival and giving calendar, company funding pipeline, and a 12-month view that puts them together.
Dates are indicative: festival dates shift between regions, and company CSR calendars differ. Nothing here replaces your CA."""
import datetime
from . import logic

# (date, title, kind, campaign idea, note). Fixed days are marked in the note; lunar dates need a panchang check.
STANDARD = [
 ("2026-12-01", "Giving Tuesday", "Fundraising window", "One-day goal with a company match", "Date from the Giving Tuesday rule (Tuesday after US Thanksgiving)"),
 ("2026-12-05", "International Volunteer Day", "Awareness day", "Thank volunteers in public; invite new ones", "Fixed date"),
 ("2026-12-25", "Christmas", "Festival", "Gift-a-donation card for relatives", "Fixed date"),
 ("2027-01-14", "Makar Sankranti and Pongal", "Festival", "Food or warm-clothing drive", "Fixed in most years; confirm"),
 ("2027-01-26", "Republic Day", "Awareness day", "Open day; volunteers in uniform", "Fixed date"),
 ("2027-02-08", "Ramadan begins (approx)", "Festival", "Food kits; zakat-eligible appeals only if your trust can receive them", "Moon-sighting decides; confirm"),
 ("2027-03-08", "Women's Day", "Awareness day", "Women's success stories; livelihood ask", "Fixed date"),
 ("2027-03-01", "80G year-end appeal starts", "Fundraising window", "Countdown to 31 March; email donors twice; call the top 20", "Financial year ends 31 March"),
 ("2027-03-10", "Eid-ul-Fitr (approx)", "Festival", "Meal kits where relevant", "Moon-sighting decides; confirm"),
 ("2027-03-22", "Holi", "Festival", "Colour packs or sweets for children", "Confirm on a panchang"),
 ("2027-04-07", "World Health Day", "Awareness day", "Health-camp appeal", "Fixed date"),
 ("2027-05-17", "Eid al-Adha (tentative)", "Festival", "Meal-kit ask where relevant", "Tentative; confirm"),
 ("2027-06-05", "World Environment Day", "Awareness day", "Company tree-planting day", "Fixed date"),
 ("2027-08-17", "Raksha Bandhan", "Festival", "Rakhi for girls' education ask", "Confirm on a panchang"),
 ("2027-08-25", "Janmashtami", "Festival", "Food distribution; children's programme", "24 or 25 Aug by region; confirm"),
 ("2027-09-04", "Ganesh Chaturthi", "Festival", "Eco-friendly idol and clean-up with a company", "Confirm on a panchang"),
 ("2027-09-05", "Teachers' Day", "Awareness day", "Thank teachers; fund a classroom", "Fixed date"),
 ("2027-09-12", "Onam", "Festival", "Sadya for the elderly", "Confirm on a panchang"),
 ("2027-10-02", "Daan Utsav begins (2 to 8 Oct)", "Fundraising window", "Week-long campaign: one project, one number", "Fixed dates"),
 ("2027-10-09", "Dussehra", "Festival", "Ask in Navratri week", "Confirm on a panchang"),
 ("2027-10-16", "World Food Day", "Awareness day", "Nutrition kit ask", "Fixed date"),
 ("2027-10-29", "Diwali (26 to 29 Oct by source)", "Festival", "Gift-a-meal; give-a-diya; corporate gifting", "Sources differ; confirm on a panchang"),
]

def add_standard_plan(c):
    have = {(r["date"], r["title"]) for r in logic.rows(c, "SELECT date, title FROM plan_calendar")}; n = 0
    for d, t, k, idea, note in STANDARD:
        if (d, t) in have: continue
        c.execute("INSERT INTO plan_calendar(date,title,kind,idea,status,notes) VALUES(?,?,?,?,?,?)", (d, t, k, idea, "Idea", note)); n += 1
    return dict(added=n)

def yearplan(c):
    """Next 12 months in one list: calendar items, company next steps and decision dates."""
    s, today, _ = logic.ctx(c); end = today + datetime.timedelta(days=366); a, b = today.isoformat(), end.isoformat(); items = []
    for r in logic.rows(c, "SELECT * FROM plan_calendar WHERE date>=? AND date<=? AND status NOT IN ('Skipped') ORDER BY date", (a, b)):
        d = datetime.date.fromisoformat(r["date"]); left = (d - today).days
        items.append(dict(date=r["date"], type="Calendar", title=r["title"], detail=r["idea"] or "", status=r["status"], prep=(0 <= left <= 28 and r["status"] in ("Idea", "Planned")), link="#/t/plan_calendar"))
    for r in logic.rows(c, "SELECT * FROM csr_pipeline WHERE stage NOT IN ('Declined')"):
        if r.get("next_date") and a <= r["next_date"] <= b:
            items.append(dict(date=r["next_date"], type="Company", title=f"{r['company']}: {r.get('next_step') or 'next step'}", detail=r["stage"], status=r["stage"], prep=False, link="#/t/csr_pipeline"))
        if r.get("decision_by") and a <= r["decision_by"] <= b:
            items.append(dict(date=r["decision_by"], type="Decision", title=f"{r['company']}: decision expected", detail=f"Asked for {int(r.get('ask') or 0):,}", status=r["stage"], prep=False, link="#/t/csr_pipeline"))
    for r in logic.rows(c, "SELECT title, due_date FROM compliance WHERE COALESCE(due_date,'')<>'' AND due_date>=? AND due_date<=?", (a, b)):
        items.append(dict(date=r["due_date"], type="Compliance", title=r["title"], detail="", status="", prep=False, link="#/t/compliance"))
    items.sort(key=lambda x: x["date"])
    pipe = logic.rows(c, "SELECT stage, COUNT(*) n, COALESCE(SUM(ask),0) ask, COALESCE(SUM(sanctioned),0) sanctioned FROM csr_pipeline GROUP BY stage")
    return dict(items=items, pipeline=pipe, as_of=a)
