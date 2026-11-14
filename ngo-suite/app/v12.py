"""v12: social media planner helpers. Caption drafts use only your own records; nothing is posted from here."""
import datetime
from . import logic, db

TEXT = {
    "English": "In the last 90 days {org} reached {n} people through {proj}. Your support makes this possible.{link}",
    "Hindi": "पिछले 90 दिनों में {org} ने {proj} के ज़रिए {n} लोगों तक मदद पहुँचाई। आपके साथ से ही यह संभव है।{link}",
    "Marathi": "गेल्या 90 दिवसांत {org} ने {proj} द्वारे {n} लोकांपर्यंत मदत पोहोचवली. तुमच्या साथीमुळेच हे शक्य झाले.{link}",
}

def draft(c, q):
    g = lambda k: (q.get(k) or [""])[0]
    s, today, _ = logic.ctx(c)
    pid = g("project_id"); lang = g("lang") or "English"
    if lang not in TEXT: lang = "English"
    proj = logic.one(c, "SELECT name FROM projects WHERE id=?", (pid,)) if pid.isdigit() else None
    since = (today - datetime.timedelta(days=90)).isoformat()
    if proj:
        n = logic.one(c, "SELECT COALESCE(SUM(people_reached),0) n FROM activities WHERE project_id=? AND date>=?", (pid, since))["n"]; name = proj["name"]
    else:
        n = logic.one(c, "SELECT COALESCE(SUM(people_reached),0) n FROM activities WHERE date>=?", (since,))["n"]; name = "our programmes"
    base = (s.get("public_url") or "").strip().rstrip("/")
    link = f"\n\nSupport us: {base}/donate.html" if base else ""
    cap = TEXT[lang].format(org=s.get("org_name") or "We", n=f"{int(n):,}", proj=name, link=link)
    return dict(caption=cap, note="Check the numbers against your records before posting. Hindi and Marathi wording should be read by a native speaker.",
                facts=dict(people=int(n), project=name, since=since))

def ideas(c):
    s, today, _ = logic.ctx(c); t = today.isoformat()
    soon = (today + datetime.timedelta(days=30)).isoformat(); recent = (today - datetime.timedelta(days=14)).isoformat(); out = []
    for r in logic.rows(c, "SELECT * FROM partner_events WHERE date>=? AND date<=? AND COALESCE(status,'')<>'Done' ORDER BY date", (t, soon)):
        out.append(dict(kind="Coming up", title=f"Invite people to: {r['title']}", date=r["date"], project_id=r.get("project_id"), media_id=None,
                        why="An event in the next 30 days. Post an invitation a week before."))
    for r in logic.rows(c, "SELECT * FROM partner_events WHERE date>=? AND date<=? AND status='Done' ORDER BY date DESC", (recent, t)):
        out.append(dict(kind="Thank you", title=f"Thank everyone who came to: {r['title']}", date=r["date"], project_id=r.get("project_id"), media_id=None,
                        why="A thank-you within two weeks. Name the company only if it agreed."))
    for r in logic.rows(c, """SELECT a.date, a.activity, a.project_id, a.people_reached, m.id media_id FROM activities a JOIN media m ON m.activity_id=a.id AND m.consent='Y'
                              WHERE a.date>=? AND a.date<=? GROUP BY a.id ORDER BY a.date DESC LIMIT 6""", (recent, t)):
        out.append(dict(kind="Photo story", title=f"Share: {r['activity']}", date=r["date"], project_id=r["project_id"], media_id=r["media_id"],
                        why=f"{int(r['people_reached'] or 0)} people reached and a photo with consent is ready."))
    for r in logic.rows(c, 'SELECT id, name, "end" FROM projects WHERE COALESCE("end",\'\')<>\'\' AND "end">=? AND "end"<=? ORDER BY "end"', (t, soon)):
        out.append(dict(kind="Last stretch", title=f"Last month of {r['name']}: ask for a final push", date=r["end"], project_id=r["id"], media_id=None,
                        why="The project ends within 30 days. Share what is done and what is still needed."))
    return dict(items=out)
