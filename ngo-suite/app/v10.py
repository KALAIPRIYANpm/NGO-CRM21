"""v10: donor page ("Your money today"), public transparency page, sponsor-an-outcome list, yearly compliance check,
standard compliance calendar, and event attendee totals. Everything is arithmetic on your own records; nothing here replaces your CA."""
import datetime, html as _h, secrets, re
from . import logic, db
from .compliance_pack import PAGE, _head, inr, fy_range

class V10Error(Exception):
    def __init__(self, status, msg):
        super().__init__(msg); self.status, self.msg = status, msg

def esc(x): return _h.escape(str(x if x is not None else ""))

# ----------------------------------------------------------------------------- event attendees
def sync_event(c, event_id):
    """When people are listed for an event, the 'came' count and the hours are the sum of that list."""
    rows = c.execute("SELECT COUNT(*) n, COALESCE(SUM(hours),0) h FROM event_people WHERE event_id=?", (event_id,)).fetchone()
    if rows["n"]:
        c.execute("UPDATE partner_events SET attended=?, hours=? WHERE id=?", (rows["n"], rows["h"], event_id))

# ----------------------------------------------------------------------------- donor page
def set_donor_portal(c, did, revoke=False):
    d = logic.one(c, "SELECT id, portal_token FROM donors WHERE id=:i", dict(i=did))
    if not d: raise V10Error(404, "Donor not found")
    tok = None if revoke else (d["portal_token"] or secrets.token_urlsafe(18))
    c.execute("UPDATE donors SET portal_token=? WHERE id=?", (tok, did))
    return dict(token=tok, path=f"/api/public/donor/{tok}" if tok else None)

def donor_page(c, token):
    d = logic.one(c, "SELECT * FROM donors WHERE portal_token=:t AND COALESCE(portal_token,'')<>''", dict(t=token))
    if not d: raise V10Error(404, "This link is not active")
    s = db.get_settings(c); o = {k[4:]: v for k, v in s.items() if k.startswith("org_")}
    gifts = logic.rows(c, "SELECT date, amount, purpose, mode, receipt_no FROM donations WHERE donor_id=:i ORDER BY date DESC LIMIT 200", dict(i=d["id"]))
    total = sum(g["amount"] for g in gifts)
    _, a, b, label = fy_range(c)
    this_fy = sum(g["amount"] for g in gifts if a <= g["date"] <= b)
    promise = logic.one(c, "SELECT amount, frequency FROM commitments WHERE donor_id=:i AND status='Active' ORDER BY id DESC LIMIT 1", dict(i=d["id"]))
    went = []
    for purpose in dict.fromkeys(g["purpose"] for g in gifts if g["purpose"]):
        p = logic.one(c, "SELECT id, name, place FROM projects WHERE name=:n", dict(n=purpose))
        if not p: continue
        reach = logic.one(c, "SELECT COALESCE(SUM(people_reached),0) n, COUNT(*) k FROM activities WHERE project_id=:i", dict(i=p["id"]))
        res = logic.rows(c, "SELECT result, unit, achieved FROM results WHERE project_id=:i AND achieved>0 ORDER BY id LIMIT 3", dict(i=p["id"]))
        bits = [f"{int(r['achieved']):,} {esc(r['result'].lower())}" for r in res]
        went.append(f"<tr><td>{esc(p['name'])}<div class='sm'>{esc(p['place'])}</div></td><td class='n'>{int(reach['n']):,}</td><td>{'; '.join(bits) or 'Work is under way'}</td></tr>")
    rows = "".join(f"<tr><td>{esc(g['date'])}</td><td>{esc(g['purpose'] or 'General support')}</td><td>{esc(g['mode'])}</td><td class='n'>{inr(g['amount'])}</td></tr>" for g in gifts) or "<tr><td colspan='4'>No gifts recorded yet</td></tr>"
    pr = f"<p>Your regular gift: <b>{inr(promise['amount'])}</b> ({esc(promise['frequency'].lower())}). Thank you for standing with us month after month.</p>" if promise else ""
    went_html = ("<h2>What your support has helped with</h2><table><tr><th>Project</th><th class='n'>People reached</th><th>Results so far</th></tr>" + "".join(went) + "</table>") if went else ""
    body = _head(o) + f"""<h2 style="text-align:center;font-size:18px">Your giving, {esc(d['name'])}</h2>
<table><tr><th>Given in all</th><th>This year ({esc(label)})</th><th>Gifts</th></tr><tr><td class="n">{inr(total)}</td><td class="n">{inr(this_fy)}</td><td class="n">{len(gifts)}</td></tr></table>{pr}
{went_html}<h2>Your gifts</h2><table><tr><th>Date</th><th>For</th><th>How</th><th class="n">Amount</th></tr>{rows}</table>
<p class="sm">Figures come from {esc(o.get('name'))}'s own records as of {datetime.date.today().isoformat()}. This page is private to you. Ask us to switch it off at any time. For tax receipts please use the receipts we sent you.</p>"""
    return PAGE.format(title=esc("Your giving to " + str(o.get("name", ""))), body=body).encode()

# ----------------------------------------------------------------------------- public transparency page
def transparency_enabled(c):
    return (db.get_settings(c).get("public_transparency") or "No") == "Yes"

def transparency_page(c):
    s = db.get_settings(c)
    if (s.get("public_transparency") or "No") != "Yes": raise V10Error(404, "Not available")
    o = {k[4:]: v for k, v in s.items() if k.startswith("org_")}
    y0, _, _, _ = fy_range(c)
    years = []
    for y in (y0, y0 - 1, y0 - 2):
        _, a, b, label = fy_range(c, y)
        r = logic.one(c, "SELECT COALESCE(SUM(CASE WHEN type='Receipt' THEN amount END),0) rin, COALESCE(SUM(CASE WHEN type='Payment' THEN amount END),0) pout FROM cash_book WHERE date BETWEEN :a AND :b", dict(a=a, b=b))
        years.append((label, r["rin"], r["pout"]))
    _, a, b, label = fy_range(c)
    heads = logic.rows(c, "SELECT COALESCE(NULLIF(head,''),'Other') head, SUM(amount) amt FROM cash_book WHERE type='Payment' AND date BETWEEN :a AND :b GROUP BY 1 ORDER BY amt DESC", dict(a=a, b=b))
    ptot = sum(h["amt"] for h in heads) or 1
    projects = logic.rows(c, """SELECT p.name, p.place, p.purpose, COALESCE(SUM(a.people_reached),0) people FROM projects p LEFT JOIN activities a ON a.project_id=p.id
                                GROUP BY p.id ORDER BY people DESC LIMIT 12""")
    y_rows = "".join(f"<tr><td>{esc(l)}</td><td class='n'>{inr(i)}</td><td class='n'>{inr(p)}</td></tr>" for l, i, p in years)
    h_rows = "".join(f"<tr><td>{esc(h['head'])}</td><td class='n'>{inr(h['amt'])}</td><td class='n'>{h['amt'] / ptot * 100:.0f}%</td></tr>" for h in heads) or "<tr><td colspan='3'>No payments recorded yet</td></tr>"
    p_rows = "".join(f"<tr><td>{esc(p['name'])}<div class='sm'>{esc(p['purpose'])}</div></td><td>{esc(p['place'])}</td><td class='n'>{int(p['people']):,}</td></tr>" for p in projects)
    note = f"<p>{esc(s.get('transparency_note'))}</p>" if s.get("transparency_note") else ""
    body = _head(o) + f"""<h2 style="text-align:center;font-size:18px">Who we are and how we use your money</h2>{note}
<h2>Money received and paid, by year</h2><table><tr><th>Year</th><th class="n">Received</th><th class="n">Paid</th></tr>{y_rows}</table>
<h2>Where the money went in {esc(label)}</h2><table><tr><th>Head</th><th class="n">Amount</th><th class="n">Share</th></tr>{h_rows}</table>
<h2>Our programmes</h2><table><tr><th>Programme</th><th>Place</th><th class="n">People reached</th></tr>{p_rows}</table>
<p class="sm">These figures come from our own records and are not audited. Audited accounts and registration papers are available on request. Updated {datetime.date.today().isoformat()}.</p>"""
    return PAGE.format(title=esc("About " + str(o.get("name", ""))), body=body).encode()

# ----------------------------------------------------------------------------- sponsor an outcome (public list)
def public_outcomes(c):
    s = db.get_settings(c)
    rows = logic.rows(c, """SELECT t.id, t.title, t.unit_cost, t.per, t.description, p.name project FROM outcomes t LEFT JOIN projects p ON p.id=t.project_id
                            WHERE t.active='Y' ORDER BY t.unit_cost""")
    return dict(intro=s.get("outcome_intro") or "Choose what your gift will do.", outcomes=rows)

# ----------------------------------------------------------------------------- yearly compliance check
KEYWORDS = [("Audit of accounts", r"audit"), ("Income tax return", r"income tax|\bitr\b|return"), ("TDS payments and returns", r"tds"),
            ("80G and 12A renewal", r"80g|12a"), ("FCRA return (only if you receive foreign money)", r"fcra"), ("Trustee or board meeting", r"meeting")]

def _default_password_users(c):
    out = []
    for u in c.execute("SELECT username, pw_hash, salt FROM users"):
        h, _ = db.hash_pw("ChangeMe123", u["salt"])
        if h == u["pw_hash"]: out.append(u["username"])
    return out

def year_check(c):
    s, today, _ = logic.ctx(c)
    items = []
    def add(area, title, status, detail, link=""): items.append(dict(area=area, title=title, status=status, detail=detail, link=link))
    # registration details
    for k, label in (("org_reg", "Registration number"), ("org_pan", "Trust PAN"), ("org_12a", "12A number"), ("org_80g", "80G number")):
        v = (s.get(k) or "").strip()
        if not v: add("Registration", label + " is blank", "warn", "Add it in Branding & setup so it prints on receipts and reports.", "#/a/branding")
        elif "sample" in v.lower(): add("Registration", label + " still has sample text", "warn", "Replace the sample text with the real number.", "#/a/branding")
    # receipts and PAN
    n = logic.one(c, "SELECT COUNT(*) n FROM donations WHERE receipt_given='N' AND date<=:d", dict(d=(today - datetime.timedelta(days=30)).isoformat()))["n"]
    add("Receipts", "Receipts waiting more than 30 days", "fix" if n else "ok", f"{n} gift(s) have no receipt marked as given." if n else "Every older gift has a receipt.", "#/t/donations")
    _, a, b, label = fy_range(c)
    n = logic.one(c, """SELECT COUNT(*) n FROM donors d WHERE COALESCE(d.id_no,'')='' AND EXISTS (SELECT 1 FROM donations n WHERE n.donor_id=d.id AND n.date BETWEEN :a AND :b)""", dict(a=a, b=b))["n"]
    add("Receipts", f"Donors with no PAN or ID recorded this year ({label})", "warn" if n else "ok", f"{n} donor(s) gave this year but have no ID number. Ask your CA what is needed for 80G." if n else "All donors who gave this year have an ID recorded.", "#/t/donors")
    # compliance calendar
    items_cal = logic.rows(c, "SELECT * FROM compliance")
    overdue = soon = 0
    for r in items_cal:
        st = logic.compliance_status(r, today)
        if st.get("cstatus") == "Overdue": overdue += 1
        elif st.get("days_left") is not None and 0 <= st["days_left"] <= 30 and st.get("cstatus") != "Done": soon += 1
    add("Calendar", "Overdue items in the compliance calendar", "fix" if overdue else "ok", f"{overdue} overdue." if overdue else "Nothing overdue.", "#/t/compliance")
    add("Calendar", "Items due in the next 30 days", "warn" if soon else "ok", f"{soon} due soon." if soon else "Nothing due in the next month.", "#/t/compliance")
    titles = " | ".join((r["title"] or "").lower() for r in items_cal)
    missing = [lab for lab, rx in KEYWORDS if not re.search(rx, titles)]
    add("Calendar", "Standard yearly items in your calendar", "warn" if missing else "ok",
        ("Not in your calendar: " + "; ".join(missing) + ". Ask your CA which apply, then use 'Add the standard items'.") if missing else "All the usual items are there.", "#/t/compliance")
    # funders and funds
    n = logic.one(c, "SELECT COUNT(*) n FROM grants WHERE COALESCE(report_due,'')<>'' AND report_due<:d", dict(d=today.isoformat()))["n"]
    add("Funders", "Funder reports past their due date", "fix" if n else "ok", f"{n} grant(s) have a report due date in the past. Check each and update the date once sent." if n else "No grant report is overdue.", "#/t/grants")
    n = logic.one(c, "SELECT COUNT(*) n FROM tranches WHERE COALESCE(received_date,'')='' AND due_date<:d", dict(d=today.isoformat()))["n"]
    add("Funders", "Funder payments overdue", "warn" if n else "ok", f"{n} expected payment(s) have not arrived." if n else "No expected payment is late.", "#/t/tranches")
    neg = logic.rows(c, """SELECT f.name, f.opening + COALESCE(SUM(CASE WHEN b.type='Receipt' THEN b.amount WHEN b.type='Payment' THEN -b.amount END),0) bal
                           FROM funds f LEFT JOIN cash_book b ON b.fund_id=f.id GROUP BY f.id HAVING bal < 0""")
    add("Accounts", "Funds with a negative balance", "fix" if neg else "ok", ("Check: " + "; ".join(f"{x['name']} ({inr(x['bal'])})" for x in neg)) if neg else "No fund is below zero.", "#/r/funds")
    # people and security
    lb = s.get("last_backup") or ""
    try: age = (datetime.datetime.now() - datetime.datetime.fromisoformat(lb[:19])).days if lb else None
    except ValueError: age = None
    add("Safety", "Recent backup", "ok" if age is not None and age <= 8 else "fix", f"Last backup {lb[:10]}." if age is not None else "No backup has been made yet.", "#/a/audit")
    dp = _default_password_users(c)
    add("Safety", "Sample password still in use", "fix" if dp else "ok", ("Change the password for: " + ", ".join(dp)) if dp else "No user has the sample password.", "#/a/users")
    # governance
    last = logic.one(c, "SELECT MAX(date) d FROM decisions")["d"]
    old = (not last) or (today - datetime.date.fromisoformat(last)).days > 120
    add("Governance", "A board decision recorded in the last 4 months", "warn" if old else "ok", "Record the decisions of your last meeting." if old else f"Last recorded {last}.", "#/t/decisions")
    n = logic.one(c, "SELECT COUNT(*) n FROM decisions WHERE status='Open' AND COALESCE(due,'')<>'' AND due<:d", dict(d=today.isoformat()))["n"]
    add("Governance", "Board decisions overdue", "warn" if n else "ok", f"{n} open decision(s) are past their due date." if n else "None overdue.", "#/t/decisions")
    nr = logic.one(c, "SELECT COUNT(*) n FROM risks WHERE status<>'Closed' AND likelihood*impact>=15 AND COALESCE(mitigation,'')=''")["n"]
    add("Governance", "High risks with no plan", "fix" if nr else "ok", f"{nr} high risk(s) have nothing written under 'What we do about it'." if nr else "Every high risk has a plan.", "#/t/risks")
    ni = logic.one(c, "SELECT COUNT(*) n FROM incidents WHERE status='Open' AND date<:d", dict(d=(today - datetime.timedelta(days=30)).isoformat()))["n"]
    add("Governance", "Incidents open more than 30 days", "warn" if ni else "ok", f"{ni} incident(s) are still open." if ni else "No old open incidents.", "#/t/incidents")
    npol = logic.one(c, "SELECT COUNT(*) n FROM policies WHERE COALESCE(adopted_on,'')=''")["n"]; tot = logic.one(c, "SELECT COUNT(*) n FROM policies")["n"]
    add("Governance", "Policies adopted by the board", "warn" if (npol or not tot) else "ok", ("No policy is listed yet. Use 'Add the usual policies' on that page." if not tot else f"{npol} policy(ies) have no adoption date.") if (npol or not tot) else "Every listed policy has an adoption date.", "#/t/policies")
    nrv = logic.one(c, "SELECT COUNT(*) n FROM policies WHERE COALESCE(next_review,'')<>'' AND next_review<:d", dict(d=today.isoformat()))["n"]
    add("Governance", "Policies due for review", "warn" if nrv else "ok", f"{nrv} policy(ies) are past their review date." if nrv else "None past their review date.", "#/t/policies")
    nt = logic.one(c, "SELECT COUNT(*) n FROM trustees WHERE status='Active'")["n"]
    add("Governance", "Trustee list is filled in", "warn" if not nt else "ok", "Add your trustees or members." if not nt else f"{nt} active trustee(s) or member(s) listed.", "#/t/trustees")
    lm = logic.one(c, "SELECT MAX(date) d FROM meetings WHERE kind='AGM'")["d"]
    add("Governance", "An AGM recorded in the last 14 months", "warn" if (not lm or (today - datetime.date.fromisoformat(lm)).days > 425) else "ok", f"Last AGM recorded {lm}." if lm else "No AGM is recorded under Meetings and minutes.", "#/t/meetings")
    nb = logic.one(c, "SELECT COUNT(*) n FROM compliance WHERE COALESCE(due_date,'')=''")["n"]
    add("Calendar", "Items with no date yet", "warn" if nb else "ok", f"{nb} item(s) have no date. Fill them in when your CA confirms." if nb else "Every item has a date.", "#/t/compliance")
    add("Calendar", "CA details filled in", "warn" if not (s.get("ca_name") or "").strip() else "ok", "Your CA's name and contact are blank. Add them in Settings when you have them." if not (s.get("ca_name") or "").strip() else f"CA: {s.get('ca_name')}.", "#/a/settings")
    summary = dict(ok=sum(1 for i in items if i["status"] == "ok"), warn=sum(1 for i in items if i["status"] == "warn"), fix=sum(1 for i in items if i["status"] == "fix"))
    return dict(items=items, summary=summary, as_of=today.isoformat())

def add_standard_calendar(c):
    """Adds the usual yearly items that are not already there, with PLACEHOLDER dates. Set the real dates with your CA."""
    s, today, _ = logic.ctx(c)
    have = " | ".join((r["title"] or "").lower() for r in logic.rows(c, "SELECT title FROM compliance"))
    due = (today + datetime.timedelta(days=60)).isoformat(); n = 0
    for lab, rx in KEYWORDS:
        if re.search(rx, have): continue
        c.execute("INSERT INTO compliance(title,due_date,repeat,remind_days,notes) VALUES(?,?,?,?,?)",
                  (lab + " (check whether it applies, with your CA)", "", "Yearly", 30, "Date left blank on purpose. Fill it in when your CA confirms it."))
        n += 1
    return dict(added=n)


POLICY_STARTER = [("Conflict of interest and code of conduct", "Governance"), ("Safeguarding and child protection", "Safeguarding"),
    ("Prevention of sexual harassment (POSH)", "People"), ("Whistleblower and grievance redressal", "Governance"),
    ("Finance, procurement and travel", "Finance"), ("Anti-fraud and anti-corruption", "Finance"),
    ("Data protection and privacy", "Data and privacy"), ("Photo and story consent", "Data and privacy")]

def add_standard_policies(c):
    """Adds the eight policies most Indian NGOs are asked for, with no dates. The board adopts them; you fill the dates in."""
    have = " | ".join((r["name"] or "").lower() for r in logic.rows(c, "SELECT name FROM policies")); n = 0
    for name, kind in POLICY_STARTER:
        if name.lower() in have: continue
        c.execute("INSERT INTO policies(name,kind,notes) VALUES(?,?,?)", (name, kind, "Listed by the standard list. Write it, get the board to adopt it, then add the dates.")); n += 1
    return dict(added=n)
