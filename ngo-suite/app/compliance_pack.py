"""Year-end paperwork built from the records already in the software: donor statements for 80G claims,
donation register, utilisation certificates and a zip an auditor can open. These are DRAFTS prepared from your
records. They are not legal or tax advice and must be checked by your Chartered Accountant before they are issued."""
import csv, io, json, zipfile, datetime, html as _h
from . import logic, db, media

CASH_LIMIT = 2000        # cash gifts above this are not deductible under section 80G (check the current rule with your CA)

class PackError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg); self.status, self.msg = status, msg

def fy_range(c, fy=None):
    s, today, _ = logic.ctx(c); m = int(db.num(s, "fy_start_month", 4))
    if fy in (None, ""):
        start = logic.fy_start(today, m); y = start.year
    else:
        try: y = int(fy)
        except ValueError: raise PackError(400, "Year must be a number like 2026")
        start = datetime.date(y, m, 1)
    end = datetime.date(y + 1, m, 1) - datetime.timedelta(days=1) if m != 1 else datetime.date(y, 12, 31)
    label = f"{y}-{str(y + 1)[2:]}" if m != 1 else str(y)
    return y, start.isoformat(), end.isoformat(), label

def esc(x): return _h.escape(str(x if x is not None else ""))
def inr(v): return "₹" + f"{float(v or 0):,.2f}"

def donations(c, a, b):
    return logic.rows(c, """SELECT n.*, d.name donor, d.id_no pan, d.city, d.code donor_code, f.name fund FROM donations n JOIN donors d ON d.id=n.donor_id
                            LEFT JOIN funds f ON f.id=n.fund_id WHERE n.date BETWEEN :a AND :b ORDER BY n.date, n.id""", dict(a=a, b=b))

def _flags(r):
    f = []
    if not (r["pan"] or "").strip(): f.append("Donor PAN/ID missing")
    if (r["mode"] or "").lower() == "cash" and (r["amount"] or 0) > CASH_LIMIT: f.append(f"Cash above ₹{CASH_LIMIT:,} (not deductible under 80G; check with CA)")
    if r["receipt_given"] != "Y": f.append("Receipt not yet given")
    return "; ".join(f)

def register_csv(c, fy=None):
    y, a, b, label = fy_range(c, fy); out = io.StringIO(); w = csv.writer(out)
    w.writerow(["Receipt no", "Date", "Donor code", "Donor", "PAN / ID", "City", "Amount", "Mode", "Reference", "Purpose", "Fund type", "Fund", "Receipt given", "Check"])
    for r in donations(c, a, b):
        w.writerow([r["receipt_no"], r["date"], r["donor_code"], r["donor"], r["pan"] or "", r["city"] or "", r["amount"], r["mode"] or "", r["reference"] or "", r["purpose"] or "", r["fund_type"] or "", r["fund"] or "", r["receipt_given"] or "", _flags(r)])
    return out.getvalue().encode("utf-8-sig"), f"donation-register-{label}.csv"

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title><style>
body{{font:14px/1.5 Georgia,serif;color:#111;max-width:760px;margin:24px auto;padding:0 18px}}h1{{font-size:20px;margin:0}}h2{{font-size:15px;margin:18px 0 6px}}
table{{width:100%;border-collapse:collapse;margin:8px 0}}th,td{{border:1px solid #999;padding:5px 8px;text-align:left;font-size:13px}}td.n,th.n{{text-align:right}}
.head{{text-align:center;border-bottom:2px solid #111;padding-bottom:8px;margin-bottom:12px}}.sm{{font-size:12px;color:#444}}.draft{{border:1px dashed #a00;color:#a00;padding:6px 10px;margin:10px 0;font-size:12px}}
.sig{{display:flex;justify-content:space-between;margin-top:60px}}.sig div{{width:40%;border-top:1px solid #111;padding-top:4px;text-align:center;font-size:13px}}
@media print{{.noprint{{display:none}}body{{margin:0}}}}</style></head><body>
<div class="noprint sm" style="margin-bottom:10px">Use your browser's Print command (Ctrl+P) to print or save as PDF.</div>{body}</body></html>"""

def _head(o):
    ids = " &nbsp;·&nbsp; ".join(x for x in (f"Reg. {esc(o.get('reg'))}" if o.get("reg") else "", f"PAN {esc(o.get('pan'))}" if o.get("pan") else "", f"12A {esc(o.get('12a'))}" if o.get("12a") else "", f"80G {esc(o.get('80g'))}" if o.get("80g") else "") if x)
    return f"""<div class="head"><h1>{esc(o.get('name'))}</h1><div class="sm">{esc(o.get('address'))}</div><div class="sm">{esc(o.get('phone'))} {esc(o.get('email'))}</div><div class="sm">{ids}</div></div>"""

def donor_statement(c, donor_id, fy=None):
    y, a, b, label = fy_range(c, fy)
    d = logic.one(c, "SELECT * FROM donors WHERE id=:i", dict(i=donor_id))
    if not d: raise PackError(404, "Donor not found")
    o = logic.org_info(db.get_settings(c))
    rows = logic.rows(c, "SELECT * FROM donations WHERE donor_id=:d AND date BETWEEN :a AND :b ORDER BY date, id", dict(d=donor_id, a=a, b=b))
    if not rows: raise PackError(404, f"{d['name']} has no donations in {label}")
    total = sum(r["amount"] for r in rows); cash_over = [r for r in rows if (r["mode"] or "").lower() == "cash" and r["amount"] > CASH_LIMIT]
    trs = "".join(f"<tr><td>{esc(r['receipt_no'])}</td><td>{esc(r['date'])}</td><td>{esc(r['mode'])}</td><td>{esc(r['purpose'])}</td><td class='n'>{inr(r['amount'])}</td></tr>" for r in rows)
    note80 = (f"Our approval under section 80G: <b>{esc(o.get('80g'))}</b>. " if o.get("80g") else "") + "Whether a deduction is available depends on the law and your own situation; please check with your tax adviser."
    warn = f"<div class='draft'>Cash gifts above ₹{CASH_LIMIT:,} ({', '.join(esc(r['receipt_no']) for r in cash_over)}) are generally not eligible for the 80G deduction.</div>" if cash_over else ""
    body = _head(o) + f"""<h2 style="text-align:center">Annual donation statement · financial year {esc(label)}</h2>
<p>Received with thanks from <b>{esc(d['name'])}</b>{(', PAN/ID ' + esc(d['id_no'])) if d['id_no'] else ''}{(', ' + esc(d['city'])) if d['city'] else ''}, the following donations between {esc(a)} and {esc(b)}:</p>
<table><tr><th>Receipt no</th><th>Date</th><th>Mode</th><th>Purpose</th><th class="n">Amount</th></tr>{trs}<tr><th colspan="4">Total</th><th class="n">{inr(total)}</th></tr></table>{warn}
<p class="sm">{note80}</p><div class="sig"><div>Prepared by</div><div>Authorised signatory, {esc(o.get('head') or '')}</div></div>
<div class="draft noprint">Draft prepared from our records. Have your CA confirm the wording and the 80G/12A details before issuing.</div>"""
    return PAGE.format(title=esc(f"Statement {d['name']} {label}"), body=body).encode(), f"statement-{d['code'] or donor_id}-{label}.html"

def utilisation(c, grant_id):
    g = logic.one(c, "SELECT g.*, p.name project FROM grants g LEFT JOIN projects p ON p.id=g.project_id WHERE g.id=:i", dict(i=grant_id))
    if not g: raise PackError(404, "Grant not found")
    o = logic.org_info(db.get_settings(c))
    inst = logic.rows(c, "SELECT * FROM instalments WHERE grant_id=:g ORDER BY date", dict(g=grant_id)); spend = logic.rows(c, "SELECT * FROM grant_spend WHERE grant_id=:g ORDER BY date", dict(g=grant_id))
    heads = {}
    for r in spend: heads[r["head"] or "Other"] = heads.get(r["head"] or "Other", 0) + r["amount"]
    recd = sum(r["amount"] for r in inst); used = sum(r["amount"] for r in spend); nobill = [r for r in spend if r["bill_kept"] != "Y"]
    ih = "".join(f"<tr><td>{esc(r['date'])}</td><td>{esc(r['reference'])}</td><td class='n'>{inr(r['amount'])}</td></tr>" for r in inst) or "<tr><td colspan='3'>None</td></tr>"
    hh = "".join(f"<tr><td>{esc(k)}</td><td class='n'>{inr(v)}</td></tr>" for k, v in sorted(heads.items())) or "<tr><td colspan='2'>None</td></tr>"
    warn = f"<div class='draft'>{len(nobill)} payment(s) are marked as having no bill kept ({', '.join(esc(r['voucher_no'] or r['date']) for r in nobill[:6])}). Funders and auditors usually ask for these.</div>" if nobill else ""
    body = _head(o) + f"""<h2 style="text-align:center">Utilisation statement · grant {esc(g['code'])}</h2>
<table><tr><th>Funder</th><td>{esc(g['funder'])}</td></tr><tr><th>Project</th><td>{esc(g['project'])}</td></tr><tr><th>Grant period</th><td>{esc(g['start'])} to {esc(g['end'])}</td></tr><tr><th>Amount sanctioned</th><td>{inr(g['sanctioned'])}</td></tr></table>
<h2>Funds received</h2><table><tr><th>Date</th><th>Reference</th><th class="n">Amount</th></tr>{ih}<tr><th colspan="2">Total received</th><th class="n">{inr(recd)}</th></tr></table>
<h2>Funds used, by head</h2><table><tr><th>Head</th><th class="n">Amount</th></tr>{hh}<tr><th>Total used</th><th class="n">{inr(used)}</th></tr></table>
<table><tr><th>Balance unspent (received − used)</th><th class="n">{inr(recd - used)}</th></tr></table>{warn}
<p class="sm">Certified that the amounts above are taken from the books of the organisation and that the funds were used for the purpose of the grant.</p>
<div class="sig"><div>{esc(o.get('head') or 'Authorised signatory')}</div><div>Chartered Accountant (name, membership no.)</div></div>
<div class="draft noprint">Draft prepared from our records. Many funders have their own UC format: copy these figures into theirs. It must be certified by your CA before it is sent.</div>"""
    return PAGE.format(title=esc(f"Utilisation {g['code']}"), body=body).encode(), f"utilisation-{g['code']}.html"

def readiness(c, fy=None):
    y, a, b, label = fy_range(c, fy); d = donations(c, a, b)
    miss_pan = sorted({r["donor"] for r in d if not (r["pan"] or "").strip()})
    cash_over = [r for r in d if (r["mode"] or "").lower() == "cash" and r["amount"] > CASH_LIMIT]
    no_receipt = [r for r in d if r["receipt_given"] != "Y"]
    nobill = logic.rows(c, "SELECT voucher_no, date, paid_to, amount FROM grant_spend WHERE bill_kept<>'Y' AND date BETWEEN :a AND :b", dict(a=a, b=b))
    cl = logic.rows(c, """SELECT c.claim_no, c.status, (SELECT COUNT(*) FROM media m WHERE m.claim_id=c.id) bills FROM claims c WHERE c.date BETWEEN :a AND :b""", dict(a=a, b=b))
    s = db.get_settings(c)
    org = [l for k, l in (("org_pan", "organisation PAN"), ("org_80g", "80G approval number"), ("org_12a", "12A registration number"), ("org_reg", "registration number")) if not (s.get(k) or "").strip()]
    items = [
        dict(key="org", label="Organisation PAN, 12A, 80G and registration numbers are filled in (Settings)", bad=len(org), detail=", ".join(org), link="#/a/settings"),
        dict(key="pan", label="Every donor in this year has a PAN or ID", bad=len(miss_pan), detail=", ".join(miss_pan[:8]) + (" …" if len(miss_pan) > 8 else ""), link="#/t/donors"),
        dict(key="cash", label=f"No cash gifts above ₹{CASH_LIMIT:,} (not deductible under 80G)", bad=len(cash_over), detail=", ".join(r["receipt_no"] for r in cash_over[:8]), link="#/t/donations"),
        dict(key="receipt", label="Every donation has a receipt given", bad=len(no_receipt), detail=", ".join(r["receipt_no"] for r in no_receipt[:8]), link="#/t/donations"),
        dict(key="bills", label="Every grant payment has its bill kept", bad=len(nobill), detail=", ".join(str(r["voucher_no"] or r["date"]) for r in nobill[:8]), link="#/t/grant_spend"),
        dict(key="claims", label="Every expense claim has a bill photo", bad=len([x for x in cl if not x["bills"]]), detail=", ".join(x["claim_no"] for x in cl if not x["bills"])[:80], link="#/r/claims"),
        dict(key="pending", label="No expense claims left waiting for approval or payment", bad=len([x for x in cl if x["status"] in ("Pending", "Approved")]), detail="", link="#/r/claims"),
    ]
    grants = logic.rows(c, "SELECT g.id, g.code, g.funder, g.start, g.end FROM grants g WHERE g.start<=:b AND (g.end>=:a OR g.end IS NULL OR g.end='') ORDER BY g.code", dict(a=a, b=b))
    return dict(fy=y, label=label, start=a, end=b, items=items, donations=len(d), total=round(sum(r["amount"] for r in d), 2), grants=grants,
                donors=logic.rows(c, "SELECT DISTINCT d.id, d.name, d.code FROM donations n JOIN donors d ON d.id=n.donor_id WHERE n.date BETWEEN :a AND :b ORDER BY d.name", dict(a=a, b=b)))

def audit_pack(c, fy=None):
    y, a, b, label = fy_range(c, fy); mem = io.BytesIO(); z = zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED); P = dict(a=a, b=b)
    def write_csv(name, sql, cols=None):
        rows = logic.rows(c, sql, P); out = io.StringIO(); w = csv.writer(out)
        keys = cols or (list(rows[0]) if rows else ["(no rows)"]); w.writerow(keys)
        for r in rows: w.writerow([r.get(k, "") for k in keys])
        z.writestr(name, out.getvalue().encode("utf-8-sig")); return len(rows)
    z.writestr(f"donation-register-{label}.csv", register_csv(c, fy)[0])
    n_cb = write_csv("cash-book.csv", "SELECT t.date, t.voucher_no, t.type, f.name fund, t.head, t.party, t.mode, t.amount, t.note, t.source FROM cash_book t JOIN funds f ON f.id=t.fund_id WHERE t.date BETWEEN :a AND :b ORDER BY t.date, t.id")
    write_csv("grant-instalments.csv", "SELECT i.date, g.code grant_code, g.funder, i.reference, i.amount, i.note FROM instalments i JOIN grants g ON g.id=i.grant_id WHERE i.date BETWEEN :a AND :b ORDER BY i.date")
    write_csv("grant-spend.csv", "SELECT s.date, g.code grant_code, s.head, s.voucher_no, s.paid_to, s.amount, s.bill_kept FROM grant_spend s JOIN grants g ON g.id=s.grant_id WHERE s.date BETWEEN :a AND :b ORDER BY s.date")
    write_csv("expense-claims.csv", "SELECT claim_no, date, claimant, category, amount, description, status, reviewed_by, reviewed_on, remark, paid_on, cash_book_id FROM claims WHERE date BETWEEN :a AND :b ORDER BY id")
    # fund summary: opening + receipts - payments
    out = io.StringIO(); w = csv.writer(out); w.writerow(["Fund", "Type", "Opening", "Receipts", "Payments", "Closing"])
    for f in logic.rows(c, "SELECT * FROM funds ORDER BY name"):
        pre = logic.one(c, "SELECT COALESCE(SUM(CASE WHEN type='Receipt' THEN amount ELSE -amount END),0) v FROM cash_book WHERE fund_id=:f AND date<:a", dict(f=f["id"], a=a))["v"]
        cur = logic.one(c, "SELECT COALESCE(SUM(CASE WHEN type='Receipt' THEN amount END),0) r, COALESCE(SUM(CASE WHEN type='Payment' THEN amount END),0) p FROM cash_book WHERE fund_id=:f AND date BETWEEN :a AND :b", dict(f=f["id"], a=a, b=b))
        op = (f["opening"] or 0) + pre; w.writerow([f["name"], f["type"], round(op, 2), round(cur["r"], 2), round(cur["p"], 2), round(op + cur["r"] - cur["p"], 2)])
    z.writestr("fund-summary.csv", out.getvalue().encode("utf-8-sig"))
    nb = 0
    for m in logic.rows(c, "SELECT m.*, c.claim_no FROM media m JOIN claims c ON c.id=m.claim_id WHERE c.date BETWEEN :a AND :b AND m.kind='photo' ORDER BY m.id", P):
        try:
            with open(media.abspath(m["file"]), "rb") as fh: z.writestr(f"bills/{m['claim_no']}_{m['id']}.{m['file'].rsplit('.', 1)[-1]}", fh.read()); nb += 1
        except (OSError, media.MediaError): pass
    for g in readiness(c, fy)["grants"]:
        data, name = utilisation(c, g["id"]); z.writestr(f"utilisation/{name}", data)
    z.writestr("README.txt", f"""Audit pack, financial year {label} ({a} to {b})
Prepared {datetime.date.today().isoformat()} from the NGO Suite records.

donation-register-*.csv   every donation with donor PAN/ID and a "Check" column (missing PAN, cash above Rs {CASH_LIMIT}, receipt not given)
cash-book.csv             {n_cb} cash book lines
fund-summary.csv          opening, receipts, payments and closing for every fund
grant-instalments.csv, grant-spend.csv
expense-claims.csv        with approver, date and the cash book entry it was paid through
bills/                    {nb} bill photos attached to expense claims
utilisation/              a draft utilisation statement per grant active in the year (open in a browser, print)

These are drafts prepared from the records. They are not legal or tax advice. Your Chartered Accountant must review
and certify before anything is filed or issued. Photos and other documents kept outside the software are not included.
""")
    z.close(); return mem.getvalue(), f"audit-pack-{label}.zip"
