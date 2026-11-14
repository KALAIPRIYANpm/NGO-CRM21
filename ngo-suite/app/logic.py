"""Business logic and reports. Everything here is read-only and derived from the registers."""
import datetime, math
from .db import get_settings, num, asof

def rows(c, sql, p=None):
    return [dict(r) for r in c.execute(sql, p or {})]

def one(c, sql, p=None):
    r = c.execute(sql, p or {}).fetchone()
    return dict(r) if r else None

def ctx(c):
    s = get_settings(c)
    today = asof(s)
    return s, today, dict(today=today.isoformat(), repeat_gifts=num(s, "repeat_gifts", 2), ending_soon_days=num(s, "ending_soon_days", 30),
                          extra_hour_rate=num(s, "extra_hour_rate", 60), travel_per_km=num(s, "travel_per_km", 5),
                          grant_slow_gap=num(s, "grant_slow_gap", 0.3))

def asof_date(c):
    return asof(get_settings(c))

def _next_birthday(bday, today):
    """Next occurrence on/after today of an ISO birthday; 29 Feb falls on 28 Feb in non-leap years."""
    try:
        b = datetime.date.fromisoformat(bday)
    except (TypeError, ValueError):
        return None
    def on(y):
        try: return datetime.date(y, b.month, b.day)
        except ValueError: return datetime.date(y, 2, 28)
    d = on(today.year)
    if d < today: d = on(today.year + 1)
    return b, d

def birthday_people(c, days=30):
    """Donors and active team members with a birthday in the next `days` days (0 = today only)."""
    today = asof_date(c)
    out = []
    for tbl, kind, extra in (("donors", "Donor", ""), ("team", "Team", " AND active='Y'")):
        for r in c.execute(f"SELECT id, name, email, birthday, wishes FROM {tbl} WHERE COALESCE(birthday,'')<>''{extra}"):
            nb = _next_birthday(r["birthday"], today)
            if not nb: continue
            b, d = nb
            away = (d - today).days
            if away > days: continue
            sent = c.execute("SELECT 1 FROM email_log WHERE kind='birthday' AND tbl=? AND row_id=? AND year=? AND status='sent'", (tbl, r["id"], d.year)).fetchone() is not None
            out.append(dict(tbl=tbl, kind=kind, id=r["id"], name=r["name"], email=r["email"] or "", wishes=r["wishes"] or "Y", birthday=r["birthday"],
                            next_date=d.isoformat(), days_away=away, turning=(d.year - b.year) if b.year > 1930 else None, sent=sent))
    out.sort(key=lambda x: (x["days_away"], x["name"].lower()))
    return out

def _add_months(d, n):
    import calendar
    y, m = divmod(d.month - 1 + n, 12); y += d.year; m += 1
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

def compliance_status(row, today):
    """Next due date, days left and status of a compliance item (repeating items roll forward once marked done)."""
    try: due = datetime.date.fromisoformat(row["due_date"])
    except (TypeError, ValueError): return dict(next_due=None, days_left=None, cstatus="")
    last = datetime.date.fromisoformat(row["last_done"]) if row.get("last_done") else None
    step = {"Monthly": 1, "Quarterly": 3, "Yearly": 12}.get(row.get("repeat"))
    if not step:
        if last and last >= due - datetime.timedelta(days=366): return dict(next_due=due.isoformat(), days_left=None, cstatus="Done")
        nd = due
    else:
        k, nd = 0, due
        while last and nd <= last: k += 1; nd = _add_months(due, k * step)
    left = (nd - today).days
    remind = row.get("remind_days") or 14
    return dict(next_due=nd.isoformat(), days_left=left, cstatus="Overdue" if left < 0 else "Due soon" if left <= remind else "Upcoming")

def compliance_list(c):
    today = asof_date(c)
    out = []
    for r in rows(c, "SELECT * FROM compliance ORDER BY (COALESCE(due_date,'')=''), due_date"):
        r.update(compliance_status(r, today)); out.append(r)
    return out

def fy_start(today, start_month=4):
    y = today.year if today.month >= start_month else today.year - 1
    return datetime.date(y, start_month, 1)

def month_add(ym, n):
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"

def last_months(today, n=12):
    cur = today.strftime("%Y-%m")
    return [month_add(cur, -i) for i in range(n - 1, -1, -1)]

def grant_pace(g, slow_gap):
    used, tg = g.get("used"), g.get("time_gone")
    if used is None or tg is None:
        return ""
    if used > 1:
        return "Over"
    return "Slow" if tg - used > slow_gap else "On pace"

def pct(a, b):
    return (a / b) if b else None

# ---------------------------------------------------------------- dashboard
def dashboard(c):
    s, today, P = ctx(c)
    fy = fy_start(today, int(num(s, "fy_start_month", 4))).isoformat()
    ym = today.strftime("%Y-%m")
    twelve = (today - datetime.timedelta(days=365)).isoformat()
    d = {}
    d["asof"] = P["today"]
    d["org"] = s.get("org_name")
    g = lambda sql, p=None: (c.execute(sql, {**P, **(p or {})}).fetchone()[0] or 0)
    d["donors"] = g("SELECT COUNT(*) FROM donors")
    d["gifts_month"] = g("SELECT SUM(amount) FROM donations WHERE substr(date,1,7)=:m", dict(m=ym))
    d["gifts_12m"] = g("SELECT SUM(amount) FROM donations WHERE date>=:d", dict(d=twelve))
    d["gifts_fy"] = g("SELECT SUM(amount) FROM donations WHERE date>=:d", dict(d=fy))
    d["avg_gift"] = g("SELECT AVG(amount) FROM donations")
    d["receipts_to_give"] = g("SELECT COUNT(*) FROM donations WHERE receipt_given='N'")
    d["thank_you_due"] = g("SELECT COUNT(*) FROM donations WHERE thank_you_sent='N'")
    d["followups_due"] = g("SELECT COUNT(*) FROM donors WHERE COALESCE(next_followup,'')<>'' AND next_followup<=:today")
    bd = birthday_people(c, 7)
    d["birthdays_today"] = sum(1 for b in bd if b["days_away"] == 0); d["birthdays_week"] = len(bd)
    d["open_projects"] = g("SELECT COUNT(*) FROM projects WHERE stage<>'Closed'")
    d["people_listed"] = g("SELECT COUNT(*) FROM beneficiaries")
    d["people_reached"] = g("SELECT SUM(people_reached) FROM activities")
    d["activities"] = g("SELECT COUNT(*) FROM activities")
    d["project_spent"] = g("SELECT SUM(spent) FROM activities")
    d["staff"] = g("SELECT COUNT(*) FROM team WHERE active='Y' AND pay_type<>'Volunteer'")
    d["volunteers"] = g("SELECT COUNT(*) FROM team WHERE active='Y' AND pay_type='Volunteer'")
    pm = payroll(c, (today - datetime.timedelta(days=7)).strftime("%Y-%m"))
    d["payroll_month"] = pm["month"]; d["payroll_net"] = pm["totals"]["net"]
    gr = grants_list(c)
    d["grants"] = len(gr)
    d["grant_sanctioned"] = sum(x["sanctioned"] for x in gr); d["grant_received"] = sum(x["received"] for x in gr)
    d["grant_spent"] = sum(x["spent"] for x in gr); d["grant_in_hand"] = sum(x["in_hand"] for x in gr)
    fl = rows(c, TABLE_SQL["funds"], P)
    d["fund_balance"] = sum(f["balance"] for f in fl)
    for t in ("General", "Restricted", "Corpus"):
        d["fund_" + t.lower()] = sum(f["balance"] for f in fl if f["type"] == t)
    d["receipts_fy"] = g("SELECT SUM(amount) FROM cash_book WHERE type='Receipt' AND date>=:d", dict(d=fy))
    d["payments_fy"] = g("SELECT SUM(amount) FROM cash_book WHERE type='Payment' AND date>=:d", dict(d=fy))
    d["surplus_fy"] = d["receipts_fy"] - d["payments_fy"]
    months = last_months(today)
    cb = {r["m"]: r for r in rows(c, "SELECT substr(date,1,7) m, SUM(CASE WHEN type='Receipt' THEN amount ELSE 0 END) r, SUM(CASE WHEN type='Payment' THEN amount ELSE 0 END) p FROM cash_book GROUP BY m")}
    dn = {r["m"]: r["a"] for r in rows(c, "SELECT substr(date,1,7) m, SUM(amount) a FROM donations GROUP BY m")}
    d["series"] = [dict(month=m, receipts=cb.get(m, {}).get("r", 0), payments=cb.get(m, {}).get("p", 0), donations=dn.get(m, 0)) for m in months]
    d["top_donors"] = rows(c, "SELECT d.name, d.code, SUM(n.amount) total, COUNT(*) gifts FROM donations n JOIN donors d ON d.id=n.donor_id GROUP BY d.id ORDER BY total DESC LIMIT 8")
    d["call_today"] = rows(c, "SELECT code, name, phone, next_followup FROM donors WHERE COALESCE(next_followup,'')<>'' AND next_followup<=:today ORDER BY next_followup LIMIT 10", P)
    d["by_purpose"] = rows(c, "SELECT COALESCE(NULLIF(purpose,''),'Unspecified') purpose, SUM(amount) total FROM donations GROUP BY 1 ORDER BY total DESC")
    alerts = []
    for f in fl:
        if f["status"] == "Below zero":
            alerts.append(dict(level="red", text=f"Fund '{f['name']}' is below zero ({f['balance']:,.0f})", link="funds"))
    for x in gr:
        if x["pace"] == "Over": alerts.append(dict(level="red", text=f"Grant {x['code']} ({x['funder']}) has spent more than sanctioned", link="grants"))
        elif x["pace"] == "Slow": alerts.append(dict(level="amber", text=f"Grant {x['code']} ({x['funder']}) is spending slower than time", link="grants"))
        if x["report_in_days"] is not None and x["report_in_days"] <= 30:
            alerts.append(dict(level="red" if x["report_in_days"] < 0 else "amber", text=(f"Report for grant {x['code']} is {-x['report_in_days']} days overdue" if x["report_in_days"] < 0 else f"Report for grant {x['code']} due in {x['report_in_days']} days"), link="grants"))
    for p in rows(c, TABLE_SQL["projects"], P):
        if p["flag"] in ("Past end", "Ending soon"):
            alerts.append(dict(level="red" if p["flag"] == "Past end" else "amber", text=f"Project '{p['name']}': {p['flag'].lower()}", link="projects"))
    n = g("SELECT COUNT(*) FROM grant_spend WHERE bill_kept='N'")
    if n: alerts.append(dict(level="amber", text=f"{n} grant payments have no bill kept", link="grant_spend"))
    if d["receipts_to_give"]: alerts.append(dict(level="amber", text=f"{d['receipts_to_give']} donation receipts still to give", link="donations"))
    n = g("SELECT COUNT(*) FROM inbox WHERE direction='in' AND read=0 AND kind='message'")
    if n: alerts.append(dict(level="amber", text=f"{n} new WhatsApp/SMS repl{'y' if n == 1 else 'ies'} waiting in the inbox", link="r/inbox"))
    for x in compliance_list(c):
        if x["cstatus"] in ("Overdue", "Due soon"):
            alerts.append(dict(level="red" if x["cstatus"] == "Overdue" else "amber", text=f"{x['title']}: " + (f"{-x['days_left']} days overdue" if x["days_left"] < 0 else f"due in {x['days_left']} days"), link="compliance"))
    if d["birthdays_today"]:
        names = ", ".join(b["name"] for b in bd if b["days_away"] == 0)
        alerts.append(dict(level="amber", text=f"Birthday today: {names}", link="r/birthdays"))
    if d["followups_due"]: alerts.append(dict(level="amber", text=f"{d['followups_due']} donors to call today", link="donors"))
    d["alerts"] = alerts
    return d

# ---------------------------------------------------------------- shared SQL (kept in sync with spec.py)
from .spec import TABLES
TABLE_SQL = {k: v["sql"] for k, v in TABLES.items()}

def grants_list(c):
    s, today, P = ctx(c)
    out = rows(c, TABLE_SQL["grants"], P)
    for g in out:
        g["pace"] = grant_pace(g, P["grant_slow_gap"])
    return out

# ---------------------------------------------------------------- payroll
def payroll(c, month):
    s, today, P = ctx(c)
    team = rows(c, "SELECT * FROM team ORDER BY code")
    att = rows(c, "SELECT * FROM attendance WHERE substr(date,1,7)=:m", dict(m=month))
    vol = rows(c, "SELECT * FROM volunteer_log WHERE substr(date,1,7)=:m", dict(m=month))
    hr, km = P["extra_hour_rate"], P["travel_per_km"]
    out = []
    for m in team:
        a = [x for x in att if x["team_id"] == m["id"]]
        v = [x for x in vol if x["team_id"] == m["id"]]
        if m["active"] != "Y" and not a and not v:
            continue
        days = sum(1 if x["attendance"] == "P" else 0.5 if x["attendance"] == "H" else 0 for x in a)
        daily = 0.0
        if m["pay_type"] == "Per day":
            for x in a:
                base = m["pay_rate"] if x["attendance"] == "P" else m["pay_rate"] / 2 if x["attendance"] == "H" else 0
                daily += round(base + (x["extra_hours"] or 0) * hr)
        travel = sum(round((x["km"] or 0) * km) + (x["other_paid"] or 0) for x in v)
        salary = m["pay_rate"] if m["pay_type"] == "Monthly" else 0
        due = round(daily + salary + travel)
        adv = sum(x["advance_paid"] or 0 for x in a)
        out.append(dict(id=m["id"], code=m["code"], name=m["name"], role=m["role"], pay_type=m["pay_type"], pay_rate=m["pay_rate"],
                        days_present=days, vol_hours=sum(x["hours"] or 0 for x in v), travel_paid=travel, salary=salary, daily_pay=daily,
                        due=due, advances=adv, net=due - adv))
    tot = dict(due=sum(r["due"] for r in out), advances=sum(r["advances"] for r in out), net=sum(r["net"] for r in out),
               travel=sum(r["travel_paid"] for r in out), vol_hours=sum(r["vol_hours"] for r in out),
               staff=sum(1 for r in out if r["pay_type"] != "Volunteer"), volunteers=sum(1 for r in out if r["pay_type"] == "Volunteer"))
    return dict(month=month, rows=out, totals=tot)

# ---------------------------------------------------------------- accounts
def trustee_report(c, month):
    s, today, P = ctx(c)
    start = month + "-01"
    funds = rows(c, TABLE_SQL["funds"], P)
    out = []
    for f in funds:
        r = one(c, """SELECT COALESCE(SUM(CASE WHEN type='Receipt' AND date<:s THEN amount WHEN type='Payment' AND date<:s THEN -amount ELSE 0 END),0) before,
                      COALESCE(SUM(CASE WHEN type='Receipt' AND substr(date,1,7)=:m THEN amount ELSE 0 END),0) rec,
                      COALESCE(SUM(CASE WHEN type='Payment' AND substr(date,1,7)=:m THEN amount ELSE 0 END),0) pay
                      FROM cash_book WHERE fund_id=:f""", dict(s=start, m=month, f=f["id"]))
        opening = f["opening"] + r["before"]
        out.append(dict(fund=f["name"], type=f["type"], opening=opening, receipts=r["rec"], payments=r["pay"], closing=opening + r["rec"] - r["pay"]))
    heads = rows(c, "SELECT COALESCE(NULLIF(head,''),'Other') head, SUM(amount) amount FROM cash_book WHERE type='Payment' AND substr(date,1,7)=:m GROUP BY 1 ORDER BY amount DESC", dict(m=month))
    rec_heads = rows(c, "SELECT COALESCE(NULLIF(head,''),'Other') head, SUM(amount) amount FROM cash_book WHERE type='Receipt' AND substr(date,1,7)=:m GROUP BY 1 ORDER BY amount DESC", dict(m=month))
    tot = {k: sum(r[k] for r in out) for k in ("opening", "receipts", "payments", "closing")}
    tot["surplus"] = tot["receipts"] - tot["payments"]
    return dict(month=month, org=org_info(s), funds=out, payment_heads=heads, receipt_heads=rec_heads, totals=tot)

def fund_dashboard(c):
    s, today, P = ctx(c)
    funds = rows(c, TABLE_SQL["funds"], P)
    by_type = {}
    for f in funds:
        t = by_type.setdefault(f["type"], dict(type=f["type"], opening=0, received=0, spent=0, balance=0))
        for k in ("opening", "received", "spent", "balance"):
            t[k] += f[k]
    months = last_months(today)
    cb = {r["m"]: r for r in rows(c, "SELECT substr(date,1,7) m, SUM(CASE WHEN type='Receipt' THEN amount ELSE 0 END) r, SUM(CASE WHEN type='Payment' THEN amount ELSE 0 END) p FROM cash_book GROUP BY m")}
    series = [dict(month=m, receipts=cb.get(m, {}).get("r", 0), payments=cb.get(m, {}).get("p", 0)) for m in months]
    for r in series: r["surplus"] = r["receipts"] - r["payments"]
    heads = rows(c, "SELECT COALESCE(NULLIF(head,''),'Other') head, SUM(amount) amount FROM cash_book WHERE type='Payment' GROUP BY 1 ORDER BY amount DESC")
    gst = None
    if s.get("gst_registered") == "Yes":
        rec = num(s, "taxable_receipts"); lim = num(s, "gst_limit")
        gst = dict(pct=num(s, "gst_pct"), limit=lim, taxable=rec, room=max(0, lim - rec))
    return dict(funds=funds, by_type=list(by_type.values()), series=series, payment_heads=heads, gst=gst)

# ---------------------------------------------------------------- dashboards for modules
def donor_dashboard(c):
    s, today, P = ctx(c)
    d = dashboard(c)
    d["by_city"] = rows(c, "SELECT COALESCE(NULLIF(d.city,''),'Unknown') city, SUM(n.amount) total FROM donations n JOIN donors d ON d.id=n.donor_id GROUP BY 1 ORDER BY total DESC LIMIT 8")
    d["by_type"] = rows(c, "SELECT COALESCE(NULLIF(d.donor_type,''),'Unknown') type, SUM(n.amount) total, COUNT(DISTINCT d.id) donors FROM donations n JOIN donors d ON d.id=n.donor_id GROUP BY 1 ORDER BY total DESC")
    d["by_fund_type"] = rows(c, "SELECT fund_type, SUM(amount) total FROM donations GROUP BY 1")
    d["levels"] = rows(c, "SELECT level, COUNT(*) n FROM (" + TABLE_SQL["donors"] + ") GROUP BY level", P)
    return d

def project_dashboard(c):
    s, today, P = ctx(c)
    ps = rows(c, TABLE_SQL["projects"] + " ORDER BY t.name", P)
    stages = [r["value"] for r in c.execute("SELECT value FROM lists WHERE kind='stage' ORDER BY id")]
    board = {st: [dict(id=p["id"], name=p["name"], place=p["place"], lead=p["lead"], reach=p["reach"], used=p["used"], flag=p["flag"]) for p in ps if p["stage"] == st] for st in stages}
    gender = rows(c, "SELECT COALESCE(NULLIF(gender,''),'Unknown') k, COUNT(*) n FROM beneficiaries GROUP BY 1")
    village = rows(c, "SELECT COALESCE(NULLIF(village,''),'Unknown') k, COUNT(*) n FROM beneficiaries GROUP BY 1 ORDER BY n DESC LIMIT 8")
    age = rows(c, "SELECT COALESCE(NULLIF(age_group,''),'Unknown') k, COUNT(*) n FROM beneficiaries GROUP BY 1")
    return dict(stages=stages, board=board, projects=ps, gender=gender, village=village, age=age,
                totals=dict(open=sum(1 for p in ps if p["stage"] != "Closed"), listed=sum(p["people_listed"] for p in ps),
                            spent=sum(p["spent"] for p in ps), budget=sum(p["budget"] for p in ps),
                            ending=sum(1 for p in ps if p["flag"] == "Ending soon")))

# ---------------------------------------------------------------- documents
def org_info(s):
    o = {k[4:]: s.get(k, "") for k in s if k.startswith("org_")}
    o["color"] = s.get("brand_color") or "#0f5e63"; o["product"] = s.get("brand_product") or "NGO Suite"
    o["logo"] = ("/api/public/logo?v=" + s["brand_logo_ver"]) if s.get("brand_logo_ver") else ""
    return o

def _lines_total(lines):
    return round(sum(l["amount"] for l in lines), 2)

def print_receipt(c, donation_id):
    s, today, P = ctx(c)
    r = one(c, TABLE_SQL["donations"] + " WHERE t.id=:i", dict(i=donation_id))
    if not r: return None
    donor = one(c, "SELECT * FROM donors WHERE id=:i", dict(i=r["donor_id"]))
    fmt = one(c, "SELECT * FROM doc_formats WHERE name='Donation Receipt'")
    return dict(kind="receipt", org=org_info(s), format=fmt, donation=r, donor=donor, words=amount_words(r["amount"]))

def print_record(c, record_id, fmt_name):
    s, today, P = ctx(c)
    r = one(c, TABLE_SQL["records"] + " WHERE t.id=:i", dict(i=record_id))
    if not r: return None
    fmt = one(c, "SELECT * FROM doc_formats WHERE name=:n", dict(n=fmt_name))
    if not fmt: return None
    lines = rows(c, TABLE_SQL["record_lines"] + " WHERE t.record_id=:i ORDER BY t.id", dict(i=record_id))
    return dict(kind="record", org=org_info(s), format=fmt, record=r, lines=lines, lines_total=_lines_total(lines), words=amount_words(r["amount"]))

def print_donor_statement(c, donor_id):
    s, today, P = ctx(c)
    d = one(c, "SELECT * FROM donors WHERE id=:i", dict(i=donor_id))
    if not d: return None
    gifts = rows(c, "SELECT receipt_no, date, purpose, mode, amount FROM donations WHERE donor_id=:i ORDER BY date", dict(i=donor_id))
    fmt = one(c, "SELECT * FROM doc_formats WHERE name='Donor Statement'")
    return dict(kind="statement", org=org_info(s), format=fmt, donor=d, gifts=gifts, total=sum(g["amount"] for g in gifts), asof=P["today"])

def print_voucher(c, cash_id):
    s, today, P = ctx(c)
    r = one(c, TABLE_SQL["cash_book"] + " WHERE t.id=:i", dict(i=cash_id))
    if not r: return None
    fmt = one(c, "SELECT * FROM doc_formats WHERE name='Payment Voucher'")
    return dict(kind="voucher", org=org_info(s), format=fmt, entry=r, words=amount_words(r["amount"]))

def print_utilisation(c, grant_id):
    s, today, P = ctx(c)
    g = one(c, TABLE_SQL["grants"] + " WHERE t.id=:i", dict(i=grant_id))
    if not g: return None
    g["pace"] = grant_pace(g, P["grant_slow_gap"])
    ins = rows(c, "SELECT date, reference, amount FROM instalments WHERE grant_id=:i ORDER BY date", dict(i=grant_id))
    heads = rows(c, "SELECT COALESCE(NULLIF(head,''),'Other') head, COUNT(*) n, SUM(amount) amount FROM grant_spend WHERE grant_id=:i GROUP BY 1 ORDER BY amount DESC", dict(i=grant_id))
    fmt = one(c, "SELECT * FROM doc_formats WHERE name='Utilisation Certificate Format'")
    return dict(kind="utilisation", org=org_info(s), format=fmt, grant=g, instalments=ins, heads=heads, asof=P["today"])

def print_activity(c, activity_id):
    s, today, P = ctx(c)
    a = one(c, TABLE_SQL["activities"] + " WHERE t.id=:i", dict(i=activity_id))
    if not a: return None
    fmt = one(c, "SELECT * FROM doc_formats WHERE name='Activity Report'")
    return dict(kind="activity", org=org_info(s), format=fmt, activity=a)

_ONES = "Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen Fifteen Sixteen Seventeen Eighteen Nineteen".split()
_TENS = "Zero Ten Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()
def _below_100(n): return _ONES[n] if n < 20 else _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
def _below_1000(n):
    if n < 100: return _below_100(n)
    return _ONES[n // 100] + " Hundred" + ("" if n % 100 == 0 else " " + _below_100(n % 100))
def amount_words(x):
    """Indian numbering (lakh, crore): 125000 -> One Lakh Twenty Five Thousand Rupees Only."""
    x = round(float(x or 0), 2)
    rupees, paise = int(x), int(round((x - int(x)) * 100))
    if rupees == 0 and paise == 0: return "Zero Rupees Only"
    parts = []
    for div, name in ((10**7, "Crore"), (10**5, "Lakh"), (1000, "Thousand")):
        if rupees >= div:
            parts.append(_below_100(rupees // div) if rupees // div < 100 else amount_words(rupees // div).replace(" Rupees Only", "")); parts.append(name); rupees %= div
    if rupees: parts.append(_below_1000(rupees))
    w = " ".join(parts) + " Rupees" if parts else ""
    if paise: w += (" and " if w else "") + _below_100(paise) + " Paise"
    return w + " Only"

# ---------------------------------------------------------------- donor impact report
def _band(done, s):
    if done is None: return "none"
    d = done * 100
    return "green" if d >= num(s, "green_from", 90) else "light" if d >= num(s, "light_from", 70) else "yellow" if d >= num(s, "yellow_from", 50) else "red"

def _time_gone(p, today):
    try:
        a, b = datetime.date.fromisoformat(p["start"]), datetime.date.fromisoformat(p["end"])
        return max(0.0, min(1.0, (today - a).days / (b - a).days)) if b > a else None
    except (TypeError, ValueError):
        return None

def project_numbers(c, p, s, today):
    res = rows(c, TABLE_SQL["results"] + " WHERE t.project_id=:i ORDER BY t.id", dict(i=p["id"]))
    for r in res:
        r["band"] = _band(r["done"], s)
    seen, people = set(), 0
    for r in res:
        g = (r.get("people_group") or "").strip()
        if g and g not in seen:
            seen.add(g); people += r["achieved"] or 0
    capped = [min(1.0, r["done"]) for r in res if r["done"] is not None]
    work = sum(capped) / len(capped) if capped else None
    heads = rows(c, TABLE_SQL["project_spend"] + " WHERE t.project_id=:i ORDER BY t.id", dict(i=p["id"]))
    budget, used = sum(h["budget"] for h in heads), sum(h["used"] for h in heads)
    money = pct(used, budget)
    time = _time_gone(p, today)
    flag = "On track"
    if work is not None and money is not None and money - work > num(s, "money_ahead", 15) / 100: flag = "Money ahead of work"
    elif work is not None and time is not None and time - work > num(s, "time_ahead", 20) / 100: flag = "Behind schedule"
    elif work is None: flag = "No results yet"
    return dict(results=res, people=people, work=work, work_band=_band(work, s), budget=budget, used=used, balance=budget - used,
                money=money, time=time, flag=flag, heads=heads)

def impact_report(c, project_id, donor="", gift=None):
    s, today, P = ctx(c)
    p = one(c, "SELECT * FROM projects WHERE id=:i", dict(i=project_id))
    if not p: return None
    n = project_numbers(c, p, s, today)
    total_used = n["used"]
    per100 = [dict(head=h["head"], used=h["used"], share=(h["used"] / total_used * 100) if total_used else 0) for h in n["heads"] if h["used"]]
    split = None
    if gift:
        split = [dict(head=x["head"], amount=round(gift * x["share"] / 100)) for x in per100]
    story = None
    if any(p.get(k) for k in ("story_person", "story_before", "story_did", "story_after")):
        story = {k[6:]: p.get(k) for k in p if k.startswith("story_")}
    long_story = max(len(p.get(k) or "") for k in ("story_before", "story_did", "story_after")) > 220
    return dict(org=org_info(s), settings={k: s.get(k) for k in ("reporting_period", "prepared_by", "designation", "green_from", "light_from", "yellow_from")},
                project=dict(id=p["id"], name=p["name"], place=p["place"], purpose=p["purpose"], start=p["start"], end=p["end"], stage=p["stage"]),
                donor=donor, gift=gift, numbers=n, per100=per100, split=split, story=story, story_too_long=long_story, asof=P["today"])

def all_projects(c):
    s, today, P = ctx(c)
    out = []
    for p in rows(c, "SELECT * FROM projects WHERE stage<>'Closed' ORDER BY name"):
        n = project_numbers(c, p, s, today)
        out.append(dict(id=p["id"], name=p["name"], place=p["place"], stage=p["stage"], people=n["people"], used=n["used"], budget=n["budget"],
                        work=n["work"], money=n["money"], time=n["time"], flag=n["flag"], band=n["work_band"]))
    tot = dict(projects=len(out), people=sum(x["people"] for x in out), used=sum(x["used"] for x in out),
               work=(lambda v: sum(v) / len(v) if v else None)([x["work"] for x in out if x["work"] is not None]),
               need_look=sum(1 for x in out if x["flag"] in ("Money ahead of work", "Behind schedule")))
    return dict(org=org_info(s), settings={k: s.get(k) for k in ("reporting_period", "green_from", "light_from", "yellow_from", "money_ahead", "time_ahead")}, projects=out, totals=tot, asof=P["today"])

# ---------------------------------------------------------------- budget & planning tools
def _roundup(x, step):
    return math.ceil(x / step) * step if step and step > 0 else x

def project_budget(c, project_id, s):
    lines = rows(c, TABLE_SQL["budget_lines"] + " WHERE t.project_id=:i ORDER BY t.id", dict(i=project_id))
    grp = {}
    for l in lines:
        grp[l["grp"] or "Other"] = grp.get(l["grp"] or "Other", 0) + l["amount"]
    total_lines = sum(grp.values())
    cont = round(total_lines * num(s, "contingency", 0.05))
    total = _roundup(total_lines + cont, num(s, "round_up", 100))
    return dict(lines=lines, groups=grp, lines_total=total_lines, contingency=cont, total=total)

def budget_tools(c, project_id=None):
    s, today, P = ctx(c)
    projects = rows(c, "SELECT * FROM projects ORDER BY name")
    if not projects:
        return dict(error="Add a project first")
    sel = next((p for p in projects if p["id"] == project_id), None) or next((p for p in projects if str(p["id"]) == s.get("tool_project_id")), None) or projects[0]
    t = {}
    # 01 Project budget builder
    b = project_budget(c, sel["id"], s)
    months = sel["months"] or 12
    t["t01"] = dict(project=sel["name"], funder=sel["funder"], people=sel["target_people"], months=months, groups=b["groups"], lines=len(b["lines"]),
                    lines_total=b["lines_total"], contingency=b["contingency"], total=b["total"], per_month=b["total"] / months if months else 0,
                    contingency_pct=num(s, "contingency"), round_up=num(s, "round_up"))
    # all project budgets (used by several tools)
    allb = {p["id"]: project_budget(c, p["id"], s) for p in projects}
    # 02 Cost per beneficiary
    people = sel["target_people"] or 0
    limit = num(s, "limit_per_person"); sessions = num(s, "sessions_per_person", 12)
    prog = b["groups"].get("Programme", 0)
    cpp = b["total"] / people if people else 0
    t["t02"] = dict(cost_per_person=cpp, direct_per_person=prog / people if people else 0, per_month=cpp / months if months else 0,
                    per_session=cpp / sessions if sessions else 0, direct_share=prog / b["total"] if b["total"] else 0,
                    reach_at_limit=int(b["total"] // limit) if limit else 0, limit=limit, sessions=sessions,
                    verdict="Within your limit" if cpp <= limit else "Above your limit",
                    compare=[dict(project=p["name"], budget=allb[p["id"]]["total"], people=p["target_people"],
                                  per_person=(allb[p["id"]]["total"] / p["target_people"]) if p["target_people"] else 0) for p in projects[:8]])
    # 03 Fund allocation
    avail = num(s, "funds_available"); reserve = round(avail * num(s, "reserve_pct", 0.1)); share = avail - reserve
    alloc = []; tb = sum(x["total"] for x in allb.values())
    for p in projects[:12]:
        bud = allb[p["id"]]["total"] or p["budget"] or 0
        want = (share * bud / tb) if (s.get("share_by") == "By budget" and tb) else share * (p["my_share_pct"] or 0)
        got = math.floor(min(bud, want))
        alloc.append(dict(project=p["name"], budget=bud, pct=p["my_share_pct"], share=got, still=bud - got, cover=pct(got, bud)))
    t["t03"] = dict(available=avail, reserve=reserve, to_share=share, all_budgets=tb, shared=sum(a["share"] for a in alloc),
                    left=share - sum(a["share"] for a in alloc), still_to_find=sum(a["still"] for a in alloc), rows=alloc,
                    cover=pct(sum(a["share"] for a in alloc), tb), share_by=s.get("share_by"))
    # 04 Restricted vs general
    funds = rows(c, TABLE_SQL["funds"], P)
    ty = {k: dict(type=k, opening=0, received=0, spent=0, balance=0) for k in ("Restricted", "General", "Corpus")}
    for f in funds:
        for k in ("opening", "received", "spent", "balance"):
            ty[f["type"]][k] += f[k]
    allbal = sum(v["balance"] for v in ty.values()); run = num(s, "running_cost_month"); keep_m = num(s, "months_to_keep", 3)
    t["t04"] = dict(types=list(ty.values()), all=allbal, free_share=pct(ty["General"]["balance"], allbal), running_cost=run,
                    months_covered=ty["General"]["balance"] / run if run else None, keep=run * keep_m, months_to_keep=keep_m,
                    short=max(0, run * keep_m - ty["General"]["balance"]), below_zero=sum(1 for f in funds if f["balance"] < 0))
    # 05 Admin cost percent
    parts = {}
    for pid, pb in allb.items():
        for k, v in pb["groups"].items(): parts[k] = parts.get(k, 0) + v
    office = num(s, "central_office_cost"); admin = parts.get("Admin", 0) + office
    need = sum(parts.values()) + office; alimit = num(s, "admin_limit", 0.15)
    t["t05"] = dict(parts={**parts, "Central office": office}, admin=admin, need=need, admin_share=pct(admin, need), work_share=pct(parts.get("Programme", 0), need),
                    fundraising_share=pct(parts.get("Fundraising", 0), need), limit=alimit, room=alimit * need - admin, over=admin > alimit * need)
    # 06 Donation target
    promised = sum(p["funds_promised"] or 0 for p in projects); build = num(s, "reserve_to_build")
    target = need + build; short = max(0, target - promised)
    avg = one(c, "SELECT AVG(amount) a FROM donations")["a"] or 0
    t["t06"] = dict(need=need, reserve_to_build=build, target=target, promised=promised, shortfall=short, per_month=short / 12, avg_gift=avg,
                    donors_to_reach=math.ceil(short / avg) if avg else None)
    # 07 Camp or event
    pp, days = num(s, "camp_people"), num(s, "camp_days", 1)
    kits = pp * num(s, "camp_kit_per_person"); food = pp * days * num(s, "camp_food_per_person_day")
    cost = num(s, "camp_venue") * days + kits + food + num(s, "camp_other"); sponsor = num(s, "camp_sponsor")
    t["t07"] = dict(people=pp, days=days, venue=num(s, "camp_venue"), kits=kits, food=food, other=num(s, "camp_other"), cost=cost,
                    per_person=cost / pp if pp else 0, sponsor=sponsor, sponsor_gap=max(0, cost - sponsor))
    # 08 Fundraising cost ratio
    ap = rows(c, TABLE_SQL["appeals"], P)
    cost_a, raised = sum(a["cost"] for a in ap), sum(a["raised"] for a in ap)
    best = min((a for a in ap if a["raised"] > 0), key=lambda a: a["cost"] / a["raised"], default=None)
    t["t08"] = dict(appeals=ap, cost=cost_a, raised=raised, net=raised - cost_a, cost_per_100=100 * cost_a / raised if raised else None, best=best["name"] if best else None)
    # 09 Salary budget
    team = rows(c, "SELECT * FROM team WHERE active='Y'")
    wd = num(s, "working_days", 26); inc = num(s, "salary_increment", 0.08)
    monthly = sum(m["pay_rate"] if m["pay_type"] == "Monthly" else m["pay_rate"] * wd if m["pay_type"] == "Per day" else 0 for m in team)
    roles = {}
    for m in team:
        if m["pay_type"] == "Volunteer": continue
        amt = m["pay_rate"] if m["pay_type"] == "Monthly" else m["pay_rate"] * wd
        roles[m["role"] or "Other"] = roles.get(m["role"] or "Other", 0) + amt
    pm = payroll(c, (today - datetime.timedelta(days=7)).strftime("%Y-%m"))
    t["t09"] = dict(staff=sum(1 for m in team if m["pay_type"] != "Volunteer"), volunteers=sum(1 for m in team if m["pay_type"] == "Volunteer"),
                    pay_month=monthly, volunteer_payback_month=pm["totals"]["travel"], cost_year=(monthly + pm["totals"]["travel"]) * 12,
                    by_role=roles, increment=inc, next_year=(monthly + pm["totals"]["travel"]) * 12 * (1 + inc))
    # 10 Grant utilisation (all grants)
    gl = grants_list(c)
    for g in gl:
        end = g["end"]; left = None
        try: left = max(0.0, (datetime.date.fromisoformat(end) - today).days / 30.4)
        except (TypeError, ValueError): pass
        g["months_left"] = left
        g["spend_per_month"] = (g["in_hand"] / left) if left else None
    t["t10"] = dict(grants=gl)
    # 11 Cash flow
    plan = rows(c, "SELECT * FROM cashflow_plan ORDER BY month")
    bal = num(s, "cash_opening"); flow = []
    for r in plan:
        bal += r["expected_in"] - r["expected_out"]
        flow.append(dict(month=r["month"], inflow=r["expected_in"], outflow=r["expected_out"], closing=bal))
    low = min(flow, key=lambda r: r["closing"], default=None)
    t["t11"] = dict(opening=num(s, "cash_opening"), months=flow, lowest=low)
    # 12 Fund balance
    planned_out = sum(r["expected_out"] for r in plan); planned_in = sum(r["expected_in"] for r in plan)
    t["t12"] = dict(funds=funds, total=sum(f["balance"] for f in funds), planned_in=planned_in, planned_out=planned_out,
                    after_plan=sum(f["balance"] for f in funds) + planned_in - planned_out)
    # 13 Corpus interest
    corpus = ty["Corpus"]["balance"]; rate = num(s, "corpus_rate", 0.07)
    t["t13"] = dict(corpus=corpus, rate=rate, per_year=corpus * rate, per_month=corpus * rate / 12, in_5_years=corpus * (1 + rate) ** 5)
    # 14 Budget vs actual
    pr = one(c, TABLE_SQL["projects"] + " WHERE t.id=:i", {**P, "i": sel["id"]})
    tg = _time_gone(sel, today)
    t["t14"] = dict(project=sel["name"], budget=b["total"], spent=pr["spent"], balance=b["total"] - pr["spent"],
                    used=pct(pr["spent"], b["total"]), time=tg,
                    verdict=None if tg is None or not b["total"] else ("Spending ahead of time" if pr["spent"] / b["total"] - tg > 0.15 else "In line"))
    # 15 Proposal budget
    over = num(s, "proposal_overhead", 0.1); own = sel["my_share_pct"] or 0
    sub = b["total"]; ov = round(sub * over); gross = sub + ov; ask = round(gross * (1 - own))
    gst = round(ask * num(s, "gst_pct", 18) / 100) if s.get("gst_registered") == "Yes" else 0
    t["t15"] = dict(project=sel["name"], lines=b["lines"], lines_total=b["lines_total"], contingency=b["contingency"], subtotal=sub, overhead_pct=over,
                    overhead=ov, gross=gross, own_pct=own, own_share=gross - ask, ask=ask, gst=gst, ask_with_gst=ask + gst, org=org_info(s), funder=sel["funder"],
                    people=sel["target_people"], months=months)
    return dict(project_id=sel["id"], projects=[dict(id=p["id"], name=p["name"]) for p in projects], tools=t,
                params={k: s.get(k) for k in ("contingency", "round_up", "sessions_per_person", "limit_per_person", "funds_available", "reserve_pct", "share_by",
                                               "central_office_cost", "admin_limit", "reserve_to_build", "running_cost_month", "months_to_keep", "camp_people",
                                               "camp_days", "camp_venue", "camp_kit_per_person", "camp_food_per_person_day", "camp_other", "camp_sponsor",
                                               "corpus_rate", "cash_opening", "salary_increment", "proposal_overhead")})
