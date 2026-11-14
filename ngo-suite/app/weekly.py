"""Manager weekly alerts: one short summary of what needs a decision this week.
Shown on screen any time, and emailed (and optionally sent to WhatsApp) on Mondays when switched on in Settings."""
import datetime, re
from . import logic, db, donorcare, journey, gateway, inbox, automation, mailer, partners
from .mailer import EMAIL_RE, MailError

def summary(c):
    s, today, P = logic.ctx(c)
    wk = (today - datetime.timedelta(days=7)).isoformat(); two = (today - datetime.timedelta(days=14)).isoformat(); tod = today.isoformat()
    items, facts = [], {}
    def add(level, text, link=""): items.append(dict(level=level, text=text, link=link))
    fu = logic.rows(c, "SELECT code, name, next_followup FROM donors WHERE COALESCE(next_followup,'')<>'' AND next_followup<:t ORDER BY next_followup", dict(t=tod))
    facts["followups_overdue"] = len(fu)
    if fu: add("amber", f"{len(fu)} donor follow-up(s) are overdue, the oldest is {fu[0]['name']} ({fu[0]['next_followup']}).", "#/r/followups")
    cl = logic.rows(c, "SELECT status, COUNT(*) n, COALESCE(SUM(amount),0) a FROM claims WHERE status IN ('Pending','Approved') GROUP BY status")
    for r in cl:
        facts["claims_" + r["status"].lower()] = r["n"]
        add("amber", f"{r['n']} expense claim(s) {'waiting for approval' if r['status'] == 'Pending' else 'approved but not yet paid'}, ₹{r['a']:,.0f} in all.", "#/r/claims")
    quiet = logic.rows(c, """SELECT p.name, COALESCE(MAX(a.date),'') last FROM projects p LEFT JOIN activities a ON a.project_id=p.id
                             WHERE p.stage IN ('Started','Running') GROUP BY p.id HAVING COALESCE(MAX(a.date),'')<:w ORDER BY last""", dict(w=two))
    facts["projects_quiet"] = len(quiet)
    if quiet: add("red", f"{len(quiet)} running project(s) have logged no activity for 14 days: " + ", ".join(q["name"] for q in quiet[:4]) + ("…" if len(quiet) > 4 else "") + ".", "#/r/allprojects")
    lp = donorcare.lapse(c, 500); sl = [d for d in lp["donors"] if d["status"] != "Due for a thank-you or update"]
    facts["donors_slipping"] = len(sl)
    if sl: add("amber", f"{len(sl)} donor(s) are slipping or lapsed (about ₹{lp['value_at_risk']:,} a year at risk). Top: {sl[0]['name']}.", "#/r/lapse")
    bd = donorcare.board(c)["summary"]
    facts["promises_late"] = bd["late"]
    if bd["late"]: add("red", f"{bd['late']} regular-giving promise(s) are late, about ₹{bd['owed']:,} not yet received.", "#/r/promises")
    if bd["due"]: add("blue", f"{bd['due']} regular-giving promise(s) fall due this week.", "#/r/promises")
    st = journey.stale(c)
    facts["people_unseen"] = st["count"]
    if st["count"]: add("amber", f"{st['count']} active beneficiaries have had no recorded step for {st['days']}+ days.", "#/r/journey")
    tk = partners.tracker(c)["summary"]; facts["funder_payments_overdue"] = tk["overdue"]
    if tk["overdue"]: add("red", f"{tk['overdue']} funder payment(s) are overdue, ₹{tk['overdue_amount']:,} in all.", "#/t/tranches")
    od = logic.one(c, "SELECT COUNT(*) n FROM decisions WHERE status='Open' AND COALESCE(due,'')<>'' AND due<:t", dict(t=tod))["n"]; facts["decisions_overdue"] = od
    if od: add("amber", f"{od} board decision(s) are past their due date.", "#/t/decisions")
    ren = [r for r in partners.pipeline(c)["items"] if any(f.startswith("Renewal") for f in r["flags"])]; facts["partner_renewals"] = len(ren)
    if ren: add("amber", f"{len(ren)} company renewal(s) are near or past: " + ", ".join(r["name"] for r in ren[:3]) + ("…" if len(ren) > 3 else "") + ".", "#/r/partners")
    dl = automation.deadline_triggers(c)
    facts["deadlines"] = len(dl)
    for t in dl[:6]: add(t.get("level", "amber"), t["text"] + ".", "#/t/compliance" if t["tbl"].startswith("compliance") else "#/r/grants")
    try: un = inbox.unread(c)
    except Exception: un = 0
    facts["inbox_unread"] = un
    if un: add("blue", f"{un} WhatsApp/SMS repl{'y' if un == 1 else 'ies'} waiting in the inbox.", "#/r/inbox")
    g = logic.one(c, "SELECT COUNT(*) n, COALESCE(SUM(amount),0) a FROM donations WHERE date>=:w AND date<=:t", dict(w=wk, t=tod))
    nb = logic.one(c, "SELECT COUNT(*) n FROM beneficiaries WHERE date_joined>=:w AND date_joined<=:t", dict(w=wk, t=tod))
    act = logic.one(c, "SELECT COUNT(*) n, COALESCE(SUM(people_reached),0) p FROM activities WHERE date>=:w AND date<=:t", dict(w=wk, t=tod))
    week = dict(donations=g["n"], donated=g["a"], new_people=nb["n"], activities=act["n"], reached=act["p"])
    order = {"red": 0, "amber": 1, "blue": 2}; items.sort(key=lambda i: order[i["level"]])
    return dict(date=tod, from_date=wk, items=items, week=week, facts=facts, clear=not items)

def text(sm, org):
    L = [f"{org.get('name')} · weekly summary · {sm['date']}", ""]
    w = sm["week"]
    L.append(f"This week: {w['donations']} gift(s) worth ₹{w['donated']:,.0f}; {w['new_people']} new people enrolled; {w['activities']} activities reaching {w['reached']} people.")
    L.append("")
    if sm["clear"]: L.append("Nothing needs your attention. Well done.")
    else:
        L.append("NEEDS YOUR ATTENTION")
        L += [f"  - {i['text']}" for i in sm["items"]]
    return "\n".join(L)

def html(sm, org):
    body = f"<p>{automation.E(text(sm, org).split(chr(10))[2])}</p>"
    body += "<p>Nothing needs your attention. Well done.</p>" if sm["clear"] else automation._table(["", "What"], [("●" if i["level"] == "red" else "○", i["text"]) for i in sm["items"]])
    return automation._page(org, "Weekly summary · " + sm["date"], body)

def send(c, force=False):
    s, today, _ = logic.ctx(c); org = logic.org_info(s)
    if not force and today.weekday() != 0: return dict(sent=0, note="Weekly summaries go out on Mondays.")
    sm = summary(c); year = int(today.strftime("%Y%m%d")); res = dict(sent=0, failed=0)
    to = automation.recipients(s, "weekly_to") or automation.recipients(s, "digest_to")
    if to and s.get("smtp_host"):
        a, b, errs = automation._send_each(c, s, to, f"{org.get('name')}: weekly summary {sm['date']}", text(sm, org), html(sm, org), "weekly", "weekly", automation._rid, year)
        res.update(sent=a, failed=b, errors=errs)
    nums = [x for x in re.split(r"[,;\s]+", s.get("weekly_wa_to", "") or "") if x]
    tpl = (s.get("weekly_wa_template") or "").strip()
    if nums and tpl and gateway.configured(s, "whatsapp"):
        line = f"{len(sm['items'])} item(s) need attention: " + "; ".join(i["text"] for i in sm["items"][:3]) if sm["items"] else "Nothing needs attention this week."
        for n in nums:
            key = 970000000 + (automation._rid(n) % 1000000)
            if automation._already(c, "weekly_wa", "weekly", key, year): continue
            try:
                gateway.send(s, "whatsapp", n, line[:900], [line[:900]], tpl); automation._log(c, "weekly_wa", "weekly", key, year, n, "weekly", "sent"); res["sent"] += 1
            except gateway.GatewayError as e:
                automation._log(c, "weekly_wa", "weekly", key, year, n, "weekly", "failed", str(e)); res["failed"] += 1
        c.commit()
    if not res["sent"] and not res["failed"]: res["note"] = "No recipients set. Add emails in Settings → Automation."
    return res
