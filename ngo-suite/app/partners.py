"""Corporate partners, office events, relationship risk, funder payments, cash forecast, board pack and the company page.
Everything is arithmetic on your own records. The forecast is a plan, not a promise: it only knows what you have entered."""
import calendar, datetime, html as _h, secrets, statistics
from . import logic, db, donorcare
from .compliance_pack import PAGE, _head, inr

class PartnerError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg); self.status, self.msg = status, msg

def esc(x): return _h.escape(str(x if x is not None else ""))
def _d(x): return datetime.date.fromisoformat(x)
def _month_start(d): return d.replace(day=1)
def _add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    return datetime.date(d.year + y, m + 1, 1)
def _num(s, k, default=0.0):
    try: return float(s.get(k) or default)
    except (TypeError, ValueError): return default

STAGES = ["Prospect", "Pitched", "Proposal", "Approved", "Active", "Renewal due", "Lapsed"]

# ----------------------------------------------------------------------------- partners pipeline
def pipeline(c):
    s, today, _ = logic.ctx(c); t = today.isoformat()
    rows = logic.rows(c, """SELECT t.id, t.code, t.name, t.sector, t.stage, t.expected_amount, t.renewal_date, t.last_contact, t.next_step, t.next_step_date, t.owner, t.backup_owner,
        t.contact_name, t.contact_phone, t.contact_email, t.portal_token,
        COALESCE(d.s,0) given, COALESCE(d.n,0) gifts, COALESCE(e.n,0) events, COALESCE(e.h,0) hours, COALESCE(e.a,0) attended
        FROM partners t LEFT JOIN (SELECT partner_id, SUM(amount) s, COUNT(*) n FROM donations WHERE partner_id IS NOT NULL GROUP BY partner_id) d ON d.partner_id=t.id
        LEFT JOIN (SELECT partner_id, COUNT(*) n, SUM(hours) h, SUM(attended) a FROM partner_events WHERE status='Done' GROUP BY partner_id) e ON e.partner_id=t.id
        ORDER BY t.name""")
    for r in rows:
        flags = []
        if r["stage"] not in ("Lapsed",):
            if r["renewal_date"]:
                dd = (_d(r["renewal_date"]) - today).days
                r["renew_in_days"] = dd
                if dd < 0: flags.append("Renewal date passed")
                elif dd <= 60: flags.append(f"Renewal in {dd} days")
            if r["next_step_date"] and r["next_step_date"] < t: flags.append("Next step overdue")
            if r["last_contact"] and (today - _d(r["last_contact"])).days > 60 and r["stage"] in ("Active", "Approved", "Proposal", "Pitched", "Renewal due"): flags.append("No contact for 60+ days")
            if not r["owner"]: flags.append("No owner")
            elif not r["backup_owner"]: flags.append("No backup")
        r["flags"] = flags
        r["portal_token"] = bool(r["portal_token"])
    stages = []
    for st in STAGES:
        grp = [r for r in rows if r["stage"] == st]
        stages.append(dict(stage=st, count=len(grp), expected=round(sum(r["expected_amount"] or 0 for r in grp))))
    other = [r for r in rows if r["stage"] not in STAGES]
    if other: stages.append(dict(stage="Other", count=len(other), expected=round(sum(r["expected_amount"] or 0 for r in other))))
    live = [r for r in rows if r["stage"] in ("Approved", "Active", "Renewal due")]
    return dict(items=rows, stages=stages, summary=dict(total=len(rows), live=len(live), expected_live=round(sum(r["expected_amount"] or 0 for r in live)),
        given=round(sum(r["given"] for r in rows)), hours=round(sum(r["hours"] for r in rows)), events=sum(r["events"] for r in rows),
        attention=sum(1 for r in rows if r["flags"])))

# ----------------------------------------------------------------------------- event thank-you note
def event_note(c, eid):
    e = logic.one(c, """SELECT t.*, pa.name partner, p.name project FROM partner_events t LEFT JOIN partners pa ON pa.id=t.partner_id LEFT JOIN projects p ON p.id=t.project_id WHERE t.id=:i""", dict(i=eid))
    if not e: raise PartnerError(404, "Event not found")
    s = db.get_settings(c); org = s.get("org_name", "our organisation")
    who = e["partner"] or "your team"
    bits = []
    if e["attended"]: bits.append(f"{int(e['attended'])} colleague{'s' if e['attended'] != 1 else ''} took part")
    if e["hours"]: bits.append(f"{e['hours']:g} volunteer hours were given")
    if e["raised"]: bits.append(f"₹{e['raised']:,.0f} was raised")
    done = ", and ".join(bits) if bits else "the day went ahead as planned"
    upcoming = e["status"] != "Done"
    sup = f" for {e['project']}" if e["project"] else ""
    ev = f"{e['title']} on {e['date']}" + (f" at {e['venue']}" if e["venue"] else "")
    lead = (f"Thank you for agreeing to {ev}{sup}. We look forward to it and will send the details closer to the day. " if upcoming else f"Thank you for {ev}{sup}. {done[0].upper() + done[1:]}. ")
    note = (f"Dear friends at {who},\n\n{lead}"
            f"Time and effort like this reaches people directly, and we are grateful to everyone who gives a day to it.\n"
            + (f"\n{e['note']}\n" if e["note"] else "")
            + f"\nWe would love to plan the next one with you. Please tell us what worked and what we can do better.\n\nWith thanks,\n{org}\n"
            + " · ".join(x for x in (s.get("org_phone"), s.get("org_email")) if x))
    return dict(event=e["title"], partner=e["partner"], status=e["status"], note=note)

# ----------------------------------------------------------------------------- company page (private link)
def set_portal(c, pid, revoke=False):
    p = logic.one(c, "SELECT id, portal_token FROM partners WHERE id=:i", dict(i=pid))
    if not p: raise PartnerError(404, "Partner not found")
    tok = None if revoke else (p["portal_token"] or secrets.token_urlsafe(18))
    c.execute("UPDATE partners SET portal_token=? WHERE id=?", (tok, pid))
    return dict(token=tok, path=f"/api/public/partner/{tok}" if tok else None)

def portal_page(c, token):
    p = logic.one(c, "SELECT * FROM partners WHERE portal_token=:t AND COALESCE(portal_token,'')<>''", dict(t=token))
    if not p: raise PartnerError(404, "This link is not active")
    o = {k[4:]: v for k, v in db.get_settings(c).items() if k.startswith("org_")}; o["name"] = o.get("name", "")
    gifts = logic.rows(c, "SELECT date, amount, purpose FROM donations WHERE partner_id=:i ORDER BY date DESC LIMIT 100", dict(i=p["id"]))
    ev = logic.rows(c, """SELECT t.date, t.title, t.kind, t.attended, t.hours, t.raised, pr.name project FROM partner_events t LEFT JOIN projects pr ON pr.id=t.project_id
                          WHERE t.partner_id=:i AND t.status='Done' ORDER BY t.date DESC LIMIT 100""", dict(i=p["id"]))
    tot = sum(g["amount"] for g in gifts); hrs = sum(e["hours"] or 0 for e in ev); ppl = sum(e["attended"] or 0 for e in ev)
    g_rows = "".join(f"<tr><td>{esc(g['date'])}</td><td>{esc(g['purpose'])}</td><td class='n'>{inr(g['amount'])}</td></tr>" for g in gifts) or "<tr><td colspan='3'>No gifts recorded yet</td></tr>"
    e_rows = "".join(f"<tr><td>{esc(e['date'])}</td><td>{esc(e['title'])}</td><td>{esc(e['project'])}</td><td class='n'>{int(e['attended'] or 0)}</td><td class='n'>{(e['hours'] or 0):g}</td></tr>" for e in ev) or "<tr><td colspan='5'>No events recorded yet</td></tr>"
    body = _head(o) + f"""<h2 style="text-align:center;font-size:18px">Our work together: {esc(p['name'])}</h2>
<table><tr><th>Support given</th><th>Employees who took part</th><th>Volunteer hours</th><th>Events</th></tr><tr><td class="n">{inr(tot)}</td><td class="n">{ppl:,}</td><td class="n">{hrs:g}</td><td class="n">{len(ev)}</td></tr></table>
<h2>Gifts</h2><table><tr><th>Date</th><th>Purpose</th><th class="n">Amount</th></tr>{g_rows}</table>
<h2>Events with your team</h2><table><tr><th>Date</th><th>Event</th><th>Project</th><th class="n">Came</th><th class="n">Hours</th></tr>{e_rows}</table>
<p class="sm">Figures come from {esc(o['name'])}'s own records as of {datetime.date.today().isoformat()}. This page is private to your company and can be switched off at any time. For the audited figures, please ask for our annual accounts.</p>"""
    return PAGE.format(title=esc("Our work with " + p["name"]), body=body).encode()

# ----------------------------------------------------------------------------- relationship map (key-person risk)
def relations(c):
    s, today, _ = logic.ctx(c)
    major = _num(s, "major_donor_min", 50000)
    items = []
    for r in c.execute("""SELECT d.id, d.code, d.name, d.owner, d.backup_owner, d.handover_note, COALESCE(g.total,0) total, g.last
                          FROM donors d LEFT JOIN (SELECT donor_id, SUM(amount) total, MAX(date) last FROM donations GROUP BY donor_id) g ON g.donor_id=d.id
                          WHERE COALESCE(g.total,0)>=? ORDER BY g.total DESC""", (major,)):
        items.append(dict(kind="Major donor", id=r["id"], name=r["name"], code=r["code"], value=round(r["total"]), owner=r["owner"] or "", backup=r["backup_owner"] or "",
                          handover=bool(r["handover_note"]), last=r["last"] or "", link="#/t/donors"))
    for r in c.execute("SELECT * FROM partners WHERE stage IN ('Approved','Active','Renewal due','Proposal') ORDER BY expected_amount DESC"):
        items.append(dict(kind="Company", id=r["id"], name=r["name"], code=r["code"], value=round(r["expected_amount"] or 0), owner=r["owner"] or "", backup=r["backup_owner"] or "",
                          handover=bool(r["handover_note"]), last=r["last_contact"] or "", link="#/t/partners"))
    for r in c.execute("SELECT * FROM grants ORDER BY sanctioned DESC"):
        items.append(dict(kind="Funder", id=r["id"], name=r["funder"], code=r["code"], value=round(r["sanctioned"] or 0), owner=r["owner"] or "", backup=r["backup_owner"] or "",
                          handover=False, last="", link="#/t/grants"))
    for it in items:
        risk = []
        if not it["owner"]: risk.append("No owner")
        elif not it["backup"]: risk.append("No backup")
        elif it["owner"].strip().lower() == it["backup"].strip().lower(): risk.append("Backup is the same person")
        if it["kind"] != "Funder" and not it["handover"]: risk.append("No handover note")
        it["risk"] = risk
    total = sum(i["value"] for i in items) or 0
    by = {}
    for i in items:
        k = i["owner"].strip() or "(no owner)"
        by[k] = by.get(k, 0) + i["value"]
    owners = sorted(([dict(owner=k, value=v, share=round(v / total, 3) if total else 0) for k, v in by.items()]), key=lambda x: -x["value"])
    top = owners[0] if owners else None
    return dict(items=items, owners=owners, major_min=major,
                summary=dict(total=len(items), at_risk=sum(1 for i in items if any(x in i["risk"] for x in ("No owner", "No backup", "Backup is the same person"))),
                             value_at_risk=sum(i["value"] for i in items if any(x in i["risk"] for x in ("No owner", "No backup", "Backup is the same person"))),
                             top_owner=top["owner"] if top else "", top_share=top["share"] if top else 0, total_value=total))

# ----------------------------------------------------------------------------- funder payments and cash forecast
def tracker(c):
    s, today, _ = logic.ctx(c); t = today.isoformat()
    rows = logic.rows(c, """SELECT t.id, g.code grant_code, g.funder, t.due_date, t.amount, t.received_date, t.note FROM tranches t JOIN grants g ON g.id=t.grant_id ORDER BY t.due_date""")
    for r in rows:
        if r["received_date"]: r["state"] = "Received"; r["days_late"] = 0
        elif r["due_date"] < t: r["state"] = "Overdue"; r["days_late"] = (today - _d(r["due_date"])).days
        else: r["state"] = "Expected"; r["days_late"] = 0; r["in_days"] = (_d(r["due_date"]) - today).days
    open_ = [r for r in rows if r["state"] != "Received"]
    return dict(items=rows, summary=dict(overdue=sum(1 for r in rows if r["state"] == "Overdue"), overdue_amount=round(sum(r["amount"] for r in rows if r["state"] == "Overdue")),
                                         expected=round(sum(r["amount"] for r in open_)), next=(open_[0] if open_ else None)))

def _promise_dates(cm, start, end):
    step = donorcare.FREQ_DAYS.get(cm["frequency"], 1)
    try: d = _d(cm["start"])
    except (TypeError, ValueError): return []
    stop = _d(cm["end"]) if cm.get("end") else None
    out, i = [], 0
    while True:
        due = donorcare._add_months(d, step * i); i += 1
        if due > end or (stop and due > stop) or i > 600: break
        if due >= start: out.append(due)
    return out

def forecast(c, months=12):
    s, today, _ = logic.ctx(c)
    months = max(3, min(24, int(months or 12)))
    cb = logic.one(c, "SELECT COALESCE(SUM(CASE WHEN type='Receipt' THEN amount ELSE -amount END),0) bal FROM cash_book")["bal"]
    opening = logic.one(c, "SELECT COALESCE(SUM(opening),0) o FROM funds")["o"]
    bal0 = cb + opening
    restricted = 0.0
    for f in c.execute("SELECT id, type, opening FROM funds WHERE type<>'General'"):
        r = logic.one(c, "SELECT COALESCE(SUM(CASE WHEN type='Receipt' THEN amount ELSE -amount END),0) b FROM cash_book WHERE fund_id=:f", dict(f=f["id"]))["b"]
        restricted += r + (f["opening"] or 0)
    core = _num(s, "core_monthly_cost", 0)
    recent = []
    for k in range(1, 4):
        m0 = _add_months(_month_start(today), -k); m1 = _add_months(m0, 1) - datetime.timedelta(days=1)
        v = logic.one(c, "SELECT COALESCE(SUM(amount),0) p FROM cash_book WHERE type='Payment' AND date BETWEEN :a AND :b", dict(a=m0.isoformat(), b=m1.isoformat()))["p"]
        recent.append(v)
    avg_out = round(sum(recent) / 3) if any(recent) else 0
    cost_basis = "your core monthly cost setting" if core > 0 else ("your average spending over the last 3 months" if avg_out else "no spending data yet")
    out_m = core if core > 0 else avg_out
    reserve_m = _num(s, "reserve_months", 3)
    first = _month_start(today); last_day = _add_months(first, months) - datetime.timedelta(days=1)
    plan = {r["month"]: r for r in c.execute("SELECT * FROM cashflow_plan")}
    cms = [dict(r) for r in c.execute("SELECT * FROM commitments WHERE status='Active'")]
    tr = [dict(r) for r in c.execute("SELECT t.*, g.funder FROM tranches t JOIN grants g ON g.id=t.grant_id WHERE COALESCE(t.received_date,'')=''")]
    rows, bal = [], bal0
    for i in range(months):
        m0 = _add_months(first, i); m1 = _add_months(m0, 1) - datetime.timedelta(days=1); key = m0.strftime("%Y-%m")
        pr = sum(cm["amount"] for cm in cms for d in _promise_dates(cm, max(m0, today), m1) if m0 <= d <= m1)
        tin = 0.0
        for t in tr:
            due = _d(t["due_date"])
            if (i == 0 and due <= m1) or (i > 0 and m0 <= due <= m1): tin += t["amount"]
        pl = plan.get(key); pin = (pl["expected_in"] if pl else 0) or 0; pout = (pl["expected_out"] if pl else 0) or 0
        inflow = round(pr + tin + pin); outflow = round(out_m + pout)
        bal = bal + inflow - outflow
        rows.append(dict(month=key, label=m0.strftime("%b %Y"), promises=round(pr), funders=round(tin), planned_in=round(pin), inflow=inflow, outflow=outflow, balance=round(bal),
                         free=round(bal - restricted)))
    reserve = round(out_m * reserve_m)
    for r in rows: r["status"] = "Short" if r["free"] < 0 else ("Below reserve" if r["free"] < reserve else "OK")
    low = min(rows, key=lambda r: r["free"]) if rows else None
    runway = None
    if out_m > 0:
        runway = round(max(0, bal0 - restricted) / out_m, 1)
    tk = tracker(c)
    return dict(opening=round(bal0), restricted=round(restricted), free=round(bal0 - restricted), monthly_cost=round(out_m), cost_basis=cost_basis,
                reserve=reserve, reserve_months=reserve_m, rows=rows, lowest=low, runway_months=runway, funders=tk["summary"],
                notes=["Cash here means every fund in the cash book. Restricted and corpus funds are taken out to show the free cash you could use for core costs.",
                       "Money in is only what you have entered: giving promises, expected funder payments and your own Cash Flow Plan lines. Nothing is guessed.",
                       f"Money out uses {cost_basis}, plus any Money going out lines in your Cash Flow Plan."])

# ----------------------------------------------------------------------------- board pack
def board(c):
    s, today, _ = logic.ctx(c); t = today.isoformat()
    m0 = _add_months(_month_start(today), -3).isoformat()
    fy = (datetime.date(today.year if today.month >= 4 else today.year - 1, 4, 1)).isoformat()
    inc = logic.one(c, "SELECT COALESCE(SUM(amount),0) a FROM cash_book WHERE type='Receipt' AND date>=:d", dict(d=fy))["a"]
    exp = logic.one(c, "SELECT COALESCE(SUM(amount),0) a FROM cash_book WHERE type='Payment' AND date>=:d", dict(d=fy))["a"]
    by_head = logic.rows(c, "SELECT COALESCE(NULLIF(head,''),'Other') head, SUM(amount) amount FROM cash_book WHERE type='Payment' AND date>=:d GROUP BY 1 ORDER BY amount DESC LIMIT 6", dict(d=fy))
    by_src = logic.rows(c, "SELECT COALESCE(NULLIF(head,''),'Other') head, SUM(amount) amount FROM cash_book WHERE type='Receipt' AND date>=:d GROUP BY 1 ORDER BY amount DESC LIMIT 6", dict(d=fy))
    fc = forecast(c, 12); pl = pipeline(c); rl = relations(c); tk = tracker(c); bd = donorcare.board(c)["summary"]
    dec = logic.rows(c, "SELECT date, meeting, decision, owner, due FROM decisions WHERE status='Open' ORDER BY COALESCE(NULLIF(due,''),'9999'), date")
    for d in dec: d["overdue"] = bool(d["due"] and d["due"] < t)
    comp = logic.rows(c, "SELECT title, due_date FROM compliance WHERE COALESCE(due_date,'')<>'' AND due_date<=:d ORDER BY due_date LIMIT 8", dict(d=(today + datetime.timedelta(days=60)).isoformat()))
    risks = []
    if fc["lowest"] and fc["lowest"]["status"] != "OK": risks.append(f"Free cash is forecast to be {fc['lowest']['status'].lower()} in {fc['lowest']['label']} (₹{fc['lowest']['free']:,}).")
    if tk["summary"]["overdue"]: risks.append(f"{tk['summary']['overdue']} funder payment(s) are overdue, ₹{tk['summary']['overdue_amount']:,} in all.")
    if bd["late"]: risks.append(f"{bd['late']} regular-giving promise(s) are late (about ₹{bd['owed']:,}).")
    if rl["summary"]["at_risk"]: risks.append(f"{rl['summary']['at_risk']} key relationship(s) have no owner or no backup (₹{rl['summary']['value_at_risk']:,} of value).")
    if rl["summary"]["top_share"] >= 0.5 and rl["summary"]["top_owner"] != "(no owner)": risks.append(f"{round(rl['summary']['top_share'] * 100)}% of relationship value sits with one person: {rl['summary']['top_owner']}.")
    overdue_dec = sum(1 for d in dec if d["overdue"])
    if overdue_dec: risks.append(f"{overdue_dec} board decision(s) are past their due date.")
    return dict(asof=t, fy_start=fy, income=round(inc), spend=round(exp), surplus=round(inc - exp), by_head=by_head, by_source=by_src, forecast=fc, partners=pl, relations=rl, funders=tk, promises=bd, decisions=dec, compliance=comp, risks=risks)


def board_html(c, notes=""):
    b = board(c); o = {k[4:]: v for k, v in db.get_settings(c).items() if k.startswith("org_")}
    risks = "".join(f"<li>{esc(r)}</li>" for r in b["risks"]) or "<li>Nothing flagged by the records.</li>"
    heads = "".join(f"<tr><td>{esc(x['head'])}</td><td class='n'>{inr(x['amount'])}</td></tr>" for x in b["by_head"]) or "<tr><td colspan='2'>No payments recorded</td></tr>"
    srcs = "".join(f"<tr><td>{esc(x['head'])}</td><td class='n'>{inr(x['amount'])}</td></tr>" for x in b["by_source"]) or "<tr><td colspan='2'>No receipts recorded</td></tr>"
    st = "".join(f"<tr><td>{esc(x['stage'])}</td><td class='n'>{x['count']}</td><td class='n'>{inr(x['expected'])}</td></tr>" for x in b["partners"]["stages"] if x["count"]) or "<tr><td colspan='3'>No companies yet</td></tr>"
    fc = "".join(f"<tr><td>{esc(r['label'])}</td><td class='n'>{inr(r['inflow'])}</td><td class='n'>{inr(r['outflow'])}</td><td class='n'>{inr(r['free'])}</td><td>{esc(r['status'])}</td></tr>" for r in b["forecast"]["rows"])
    dec = "".join(f"<tr><td>{esc(d['date'])}</td><td>{esc(d['decision'])}</td><td>{esc(d['owner'])}</td><td>{esc(d['due'])}{' (overdue)' if d['overdue'] else ''}</td></tr>" for d in b["decisions"]) or "<tr><td colspan='4'>No open decisions</td></tr>"
    tr = "".join(f"<tr><td>{esc(r['funder'])}</td><td>{esc(r['due_date'])}</td><td class='n'>{inr(r['amount'])}</td><td>{esc(r['state'])}{(' · ' + str(r['days_late']) + ' days late') if r['state'] == 'Overdue' else ''}</td></tr>" for r in b["funders"]["items"] if r["state"] != "Received") or "<tr><td colspan='4'>None pending</td></tr>"
    f = b["forecast"]
    body = _head(o) + f"""<h2 style="text-align:center;font-size:18px">Board pack as of {esc(b['asof'])}</h2>
<h2>Things the board should look at first</h2><ul>{risks}</ul>
<h2>Money this financial year (from {esc(b['fy_start'])})</h2>
<table><tr><th>Income</th><th>Spend</th><th>Surplus or shortfall</th><th>Cash today</th><th>Of which restricted</th><th>Free cash</th></tr>
<tr><td class="n">{inr(b['income'])}</td><td class="n">{inr(b['spend'])}</td><td class="n">{inr(b['surplus'])}</td><td class="n">{inr(f['opening'])}</td><td class="n">{inr(f['restricted'])}</td><td class="n">{inr(f['free'])}</td></tr></table>
<table><tr><th>Where income came from</th><th class="n">Amount</th></tr>{srcs}</table><table><tr><th>Where money was spent</th><th class="n">Amount</th></tr>{heads}</table>
<h2>Cash forecast, next 12 months</h2><p class="sm">Monthly cost used: {inr(f['monthly_cost'])} ({esc(f['cost_basis'])}). Reserve target: {inr(f['reserve'])} ({f['reserve_months']:g} months). {('Free cash covers about ' + str(f['runway_months']) + ' months of costs today.') if f['runway_months'] is not None else ''}</p>
<table><tr><th>Month</th><th class="n">Money in</th><th class="n">Money out</th><th class="n">Free cash</th><th>Status</th></tr>{fc}</table>
<h2>Funder payments still to come</h2><table><tr><th>Funder</th><th>Due</th><th class="n">Amount</th><th>State</th></tr>{tr}</table>
<h2>Company partners</h2><table><tr><th>Stage</th><th class="n">Companies</th><th class="n">Expected this year</th></tr>{st}</table>
<p class="sm">Given so far through companies: {inr(b['partners']['summary']['given'])}. Events held: {b['partners']['summary']['events']}. Volunteer hours: {b['partners']['summary']['hours']:g}.</p>
<h2>Open decisions and actions</h2><table><tr><th>Meeting date</th><th>Decision</th><th>Owner</th><th>Due</th></tr>{dec}</table>
<h2>Statutory dates in the next 60 days</h2><table><tr><th>Item</th><th>Due</th></tr>{"".join(f"<tr><td>{esc(x['title'])}</td><td>{esc(x['due_date'])}{' (overdue)' if x['due_date'] < b['asof'] else ''}</td></tr>" for x in b['compliance']) or "<tr><td colspan='2'>Nothing due</td></tr>"}</table>
{('<h2>Notes</h2><p>' + esc(notes) + '</p>') if notes else ''}
<div class="sig"><div>Chairperson</div><div>Secretary</div></div>
<div class="draft noprint">Made from your own records on {esc(b['asof'])}. Check the figures against your accounts before it goes to the board. The forecast is only as good as what has been entered.</div>"""
    return PAGE.format(title=esc("Board pack " + b["asof"]), body=body).encode(), f"board-pack-{b['asof']}.html"
