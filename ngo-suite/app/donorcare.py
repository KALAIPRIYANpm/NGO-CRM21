"""Keeping donors: who is slipping away (lapse prediction from each donor's own giving rhythm),
and regular-giving promises (monthly / quarterly / yearly) matched against the donations you record.
Everything here is arithmetic on your own records: no outside data, no guessing from personal traits."""
import datetime, statistics, urllib.parse
from . import logic, db, langpack

FREQ_DAYS = {"Monthly": 1, "Quarterly": 3, "Half-yearly": 6, "Yearly": 12}   # in months

def _d(x): return datetime.date.fromisoformat(x)
def _add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12); y += d.year; m += 1
    import calendar
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

def first_name(n): return (n or "friend").strip().split(" ")[0]

def draft(c, kind, donor, extra=None):
    """A ready message in the donor's own language (falls back to English)."""
    s = db.get_settings(c)
    return langpack.render(kind, donor.get("language"), dict(first_name=first_name(donor.get("name") or donor.get("donor")), org=s.get("org_name", ""), contact=" · ".join(x for x in (s.get("org_phone"), s.get("org_email")) if x), upi=s.get("org_upi", ""), **(extra or {})))

def wa_link(donor, text):
    ph = "".join(ch for ch in (donor.get("phone") or "") if ch.isdigit())
    if len(ph) == 10: ph = "91" + ph
    if len(ph) < 11 or donor.get("msg_optin") == "N": return ""
    return "https://wa.me/" + ph + "?text=" + urllib.parse.quote(text)

# ----------------------------------------------------------------------------- lapse
def lapse(c, limit=300):
    s, today, _ = logic.ctx(c)
    factor = max(1.1, db.num(s, "lapse_factor", 1.5))
    gifts = {}
    for r in c.execute("SELECT donor_id, date, amount FROM donations ORDER BY date"):
        gifts.setdefault(r["donor_id"], []).append((r["date"], r["amount"]))
    promised = {r["donor_id"] for r in c.execute("SELECT donor_id FROM commitments WHERE status='Active'")}
    donors = {r["id"]: dict(r) for r in c.execute("SELECT id, code, name, phone, email, city, language, msg_optin, next_followup FROM donors")}
    out = []
    for did, g in gifts.items():
        d = donors.get(did)
        if not d or did in promised: continue
        dates = [_d(x[0]) for x in g]; last = dates[-1]; since = (today - last).days
        gaps = [(b - a).days for a, b in zip(dates, dates[1:]) if (b - a).days > 0]
        cadence = max(30, int(statistics.median(gaps))) if gaps else 365
        ratio = since / cadence
        if ratio < 1: continue
        status = "Due for a thank-you or update" if ratio < factor else "Slipping" if ratio < factor * 1.7 else "Lapsed"
        total = sum(x[1] for x in g)
        d.update(last_gift=last.isoformat(), last_amount=g[-1][1], gifts=len(g), total=total, avg=round(total / len(g)),
                 cadence_days=cadence, days_since=since, ratio=round(ratio, 2), status=status, basis="their own usual gap" if gaps else "one gift so far (assumed yearly)")
        d["message"] = draft(c, "lapse", d, dict(last_amount=f"{g[-1][1]:,.0f}", last_date=last.isoformat()))
        d["wa"] = wa_link(d, d["message"])
        out.append(d)
    out.sort(key=lambda r: (-r["total"] * min(r["ratio"], 4), r["name"]))
    summ = {k: sum(1 for r in out if r["status"].startswith(k)) for k in ("Due", "Slipping", "Lapsed")}
    return dict(factor=factor, donors=out[:limit], count=len(out), summary=summ,
                value_at_risk=round(sum(r["avg"] for r in out if r["status"] != "Due for a thank-you or update")))

# ----------------------------------------------------------------------------- giving promises
def _due_dates(cm, today):
    step = FREQ_DAYS.get(cm["frequency"], 1); start = _d(cm["start"]); end = _d(cm["end"]) if cm["end"] else None
    out, i = [], 0
    while True:
        d = _add_months(start, step * i)
        if d > today + datetime.timedelta(days=400) or (end and d > end) or i > 600: break
        out.append(d); i += 1
    return out

def evaluate(c, cm, today, grace=7):
    dues = _due_dates(cm, today)
    gifts = [dict(date=_d(r["date"]), amount=r["amount"], used=False) for r in c.execute("SELECT date, amount FROM donations WHERE donor_id=? ORDER BY date", (cm["donor_id"],))]
    step = FREQ_DAYS.get(cm["frequency"], 1); paid, missed, upcoming = [], [], None
    for d in dues:
        window_end = _add_months(d, step) - datetime.timedelta(days=1)
        hit = next((g for g in gifts if not g["used"] and d - datetime.timedelta(days=10) <= g["date"] <= window_end and g["amount"] >= cm["amount"] * 0.9), None)
        if hit: hit["used"] = True; paid.append((d, hit["date"]))
        elif d + datetime.timedelta(days=grace) < today: missed.append(d)
        elif upcoming is None: upcoming = d
    last_paid = paid[-1][1].isoformat() if paid else None
    if cm["status"] != "Active": status = cm["status"]
    elif missed: status = "Late"
    elif upcoming and (upcoming - today).days <= 7: status = "Due soon"
    elif upcoming and upcoming <= today: status = "Due now"
    else: status = "On track"
    return dict(next_due=upcoming.isoformat() if upcoming else None, days_to_due=(upcoming - today).days if upcoming else None,
                paid=len(paid), missed=len(missed), missed_dates=[m.isoformat() for m in missed[-6:]], last_paid=last_paid,
                owed=round(len(missed) * cm["amount"]), status=status)

def board(c):
    s, today, _ = logic.ctx(c)
    rows = []
    for r in c.execute("""SELECT t.*, d.name donor, d.code donor_code, d.phone, d.email, d.language, d.msg_optin FROM commitments t JOIN donors d ON d.id=t.donor_id ORDER BY d.name"""):
        cm = dict(r); cm.update(evaluate(c, cm, today))
        if cm["status"] in ("Late", "Due soon", "Due now"):
            cm["message"] = draft(c, "pledge_due", cm, dict(amount=f"{cm['amount']:,.0f}", due=(cm["missed_dates"][-1] if cm["status"] == "Late" and cm["missed_dates"] else cm["next_due"] or "")))
            cm["wa"] = wa_link(cm, cm["message"])
        rows.append(cm)
    act = [r for r in rows if r["status"] not in ("Paused", "Ended")]
    monthly = sum(r["amount"] * (1 / FREQ_DAYS.get(r["frequency"], 1)) for r in act)
    return dict(items=rows, summary=dict(active=len(act), late=sum(1 for r in rows if r["status"] == "Late"), due=sum(1 for r in rows if r["status"] in ("Due soon", "Due now")),
                                         owed=sum(r["owed"] for r in rows if r["status"] == "Late"), monthly_value=round(monthly)))

def reminders_due(c, days):
    """Active promises falling due within `days` (and not yet paid), with an email address, for the automatic reminder."""
    s, today, _ = logic.ctx(c); out = []
    for r in c.execute("SELECT t.*, d.name donor, d.email, d.language, d.wishes FROM commitments t JOIN donors d ON d.id=t.donor_id WHERE t.status='Active'"):
        cm = dict(r)
        if not cm.get("email") or cm.get("wishes") == "N": continue
        e = evaluate(c, cm, today)
        if e["next_due"] and 0 <= e["days_to_due"] <= days:
            cm.update(e); out.append(cm)
    return out
