"""v14: official documents library (with file attachments) and a CSR proposal builder made from your own records.
The proposal is a DRAFT: yellow brackets mark what only you can fill in. Have your CA and trustees read it before it goes out."""
import datetime, html as _h, os, secrets
from . import logic, db, media
from .compliance_pack import PAGE, _head, inr

class V14Error(Exception):
    def __init__(self, status, msg):
        super().__init__(msg); self.status, self.msg = status, msg

def esc(x): return _h.escape(str(x if x is not None else ""))
MAX_DOC = 10_000_000

# ---------------------------------------------------------------- documents
STANDARD_DOCS = [
 ("Registration certificate (trust deed, society or Section 8 licence)", "Registration"), ("Trust deed, MoA/AoA or bye-laws", "Registration"),
 ("Organisation PAN card", "Tax"), ("12A or 12AB registration certificate", "Tax"), ("80G approval certificate", "Tax"),
 ("CSR-1 registration (MCA)", "CSR and funders"), ("NGO Darpan unique ID", "CSR and funders"), ("FCRA registration or prior permission (only if you take foreign money)", "Foreign funds (FCRA)"),
 ("Audited accounts, last three years", "Accounts and audit"), ("Income tax return acknowledgement and audit report, last three years", "Accounts and audit"),
 ("Donation statement and donor certificate forms filed with the tax department (ask your CA)", "Tax"),
 ("Bank account proof (cancelled cheque or statement first page)", "Bank"), ("List of trustees or governing body with ID proof", "Governance"),
 ("Board resolution authorising the signatory", "Governance"), ("Annual report, last year", "Programme proof"), ("Organisation profile or brochure", "Programme proof"),
 ("Utilisation certificates issued to past funders", "CSR and funders"), ("Past sanction letters and agreements (MoUs)", "CSR and funders"),
 ("Impact or evaluation reports", "Programme proof"), ("Key staff CVs", "People and legal"), ("Core policies adopted by the board (safeguarding, POSH, finance)", "Governance"),
 ("Shops and establishment, PF, ESI or GST registration (only where they apply)", "People and legal"),
]

def add_standard_docs(c):
    have = " | ".join((r["name"] or "").lower() for r in logic.rows(c, "SELECT name FROM official_docs")); n = 0
    for name, kind in STANDARD_DOCS:
        if name.lower() in have: continue
        c.execute("INSERT INTO official_docs(name,kind,status) VALUES(?,?,'Missing')", (name, kind)); n += 1
    return dict(added=n)

def sniff_doc(first):
    if first[:4] == b"%PDF": return "pdf", "application/pdf"
    if first[:3] == b"\xff\xd8\xff": return "jpg", "image/jpeg"
    if first[:8] == b"\x89PNG\r\n\x1a\n": return "png", "image/png"
    if first[:4] == b"PK\x03\x04": return "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return None

def save_doc(rfile, length):
    """Reads a request body into docs/YYYY/random.ext. Accepts PDF, JPEG, PNG, and Word/Excel (zip based) files up to 10 MB."""
    if length <= 0: raise V14Error(400, "Empty upload")
    if length > MAX_DOC: raise V14Error(413, "File too large (limit 10 MB)")
    first = rfile.read(min(65536, length)); info = sniff_doc(first)
    if not info: raise V14Error(415, "Use a PDF, JPEG, PNG or Word file.")
    ext, mime = info; now = datetime.date.today()
    rel = f"docs/{now.year}/{secrets.token_hex(10)}.{ext}"; fp = media.abspath(rel); os.makedirs(os.path.dirname(fp), exist_ok=True)
    got = len(first)
    try:
        with open(fp, "wb") as fh:
            fh.write(first)
            while got < length:
                b = rfile.read(min(65536, length - got))
                if not b: raise V14Error(400, "Upload was cut off. Please try again.")
                fh.write(b); got += len(b)
    except BaseException:
        try: os.remove(fp)
        except OSError: pass
        raise
    return rel, mime, got

# ---------------------------------------------------------------- CSR proposal
CLAUSES = {
 "i": "Schedule VII item (i): eradicating hunger, poverty and malnutrition, promoting preventive health care and sanitation, safe drinking water",
 "ii": "Schedule VII item (ii): promoting education, including special education and employment-enhancing vocational skills, and livelihood enhancement projects",
 "iii": "Schedule VII item (iii): promoting gender equality and women's empowerment, and reducing inequalities faced by socially and economically backward groups",
 "iv": "Schedule VII item (iv): environmental sustainability, ecological balance, protection of flora and fauna, conservation of natural resources",
 "x": "Schedule VII item (x): rural development projects",
}
def mk(t): return f"<mark>[{esc(t)}]</mark>"

def proposal(c, project_id, company="", ask=0, months=12, clause="ii", notes=""):
    p = logic.one(c, "SELECT * FROM projects WHERE id=:i", dict(i=project_id))
    if not p: raise V14Error(404, "Project not found")
    s = db.get_settings(c); o = logic.org_info(s); today = datetime.date.today()
    try: months = max(1, min(60, int(months or p.get("months") or 12)))
    except (TypeError, ValueError): months = 12
    try: ask = float(ask or 0)
    except (TypeError, ValueError): ask = 0
    since = (today - datetime.timedelta(days=365)).isoformat()
    act = logic.one(c, "SELECT COUNT(*) n, COALESCE(SUM(people_reached),0) people FROM activities WHERE date>=:d", dict(d=since))
    pact = logic.one(c, "SELECT COUNT(*) n, COALESCE(SUM(people_reached),0) people FROM activities WHERE project_id=:p AND date>=:d", dict(p=project_id, d=since))
    vill = [r["village"] for r in c.execute("SELECT DISTINCT village FROM activities WHERE COALESCE(village,'')<>'' AND date>=? ORDER BY village", (since,))]
    ben = logic.one(c, "SELECT COUNT(*) total FROM beneficiaries WHERE project_id=:p", dict(p=project_id))
    gender = logic.rows(c, "SELECT COALESCE(NULLIF(gender,''),'Not recorded') k, COUNT(*) n FROM beneficiaries WHERE project_id=:p GROUP BY 1 ORDER BY n DESC", dict(p=project_id))
    results = logic.rows(c, "SELECT * FROM results WHERE project_id=:p ORDER BY id", dict(p=project_id))
    heads = logic.rows(c, "SELECT * FROM project_spend WHERE project_id=:p ORDER BY id", dict(p=project_id))
    trustees = logic.rows(c, "SELECT name, role FROM trustees WHERE status='Active' ORDER BY name")
    docs = logic.rows(c, "SELECT name, number, valid_until, status FROM official_docs WHERE status IN ('Have','Applied') ORDER BY kind, name")
    target = int(p.get("target_people") or 0); budget = float(p.get("budget") or 0)
    clause_txt = CLAUSES.get(clause, CLAUSES["ii"])
    place = p.get("place") or ""; villages = ", ".join(vill[:12])
    res = "".join(f"<tr><td>{esc(r['result'])}</td><td>{esc(r['people_group'])}</td><td class='n'>{r['target']:g} {esc(r['unit'])}</td><td>{mk('how we will check it')}</td></tr>" for r in results) \
        or f"<tr><td>{mk('result 1')}</td><td>{mk('who')}</td><td class='n'>{mk('target')}</td><td>{mk('how we will check it')}</td></tr>" * 3
    if heads:
        bud = "".join(f"<tr><td>{esc(h['head'])}</td><td class='n'>{inr(h['budget'])}</td></tr>" for h in heads); tot = sum(float(h["budget"] or 0) for h in heads)
        bud += f"<tr><th>Total</th><th class='n'>{inr(tot)}</th></tr>"
    else:
        bud = "".join(f"<tr><td>{x}</td><td class='n'>{mk('amount')}</td></tr>" for x in ("Direct programme cost", "Materials", "Staff and field costs", "Monitoring and reporting", "Overhead (state the percentage)")) + f"<tr><th>Total</th><th class='n'>{inr(ask) if ask else mk('total')}</th></tr>"
    ms = "".join(f"<tr><td>Months {i * months // 4 + 1} to {(i + 1) * months // 4}</td><td>{mk('milestone')}</td></tr>" for i in range(4))
    gtxt = ", ".join(f"{esc(g['k'])}: {g['n']}" for g in gender)
    ids = [("Registration no.", o.get("reg")), ("PAN", o.get("pan")), ("12A", o.get("12a")), ("80G", o.get("80g")), ("CSR-1 registration no.", o.get("csr1")), ("NGO Darpan ID", o.get("darpan")), ("FCRA (if applicable)", o.get("fcra"))]
    idr = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v) if v else mk('add in Settings')}</td></tr>" for k, v in ids)
    tr = "".join(f"<tr><td>{esc(t['name'])}</td><td>{esc(t['role'])}</td></tr>" for t in trustees) or f"<tr><td colspan='2'>{mk('add trustees under Governance')}</td></tr>"
    dl = "".join(f"<li>{esc(d['name'])}{(' (' + esc(d['number']) + ')') if d['number'] else ''}</li>" for d in docs) or f"<li>{mk('attach documents in the official documents library')}</li>"
    to = esc(company) if company else mk("Company name")
    body = _head(o) + f"""<h2 style="text-align:center;font-size:18px">CSR project proposal</h2>
<p style="text-align:center"><b>{esc(p['name'])}</b><br>Submitted to {to}<br><span class="sm">{today.isoformat()}</span></p>
<h2>1. Summary</h2><p>{esc(o.get('name'))} requests {inr(ask) if ask else mk('amount')} to run <b>{esc(p['name'])}</b>{(' in ' + esc(place)) if place else ' ' + mk('place')} over {months} months, for {f'{target:,}' if target else mk('number of people')} people. The project falls under {esc(clause_txt)}.</p>
<h2>2. About us</h2><p>{esc(o.get('tagline')) or mk('one line on what the organisation does')} In the last 12 months we held {int(act['n'])} activities and reached {int(act['people']):,} people{(' in ' + esc(', '.join(vill[:8]))) if vill else ''}. {mk('year founded, mission, and two lines of history')}</p>
<h2>3. The need</h2><p>{esc(p.get('purpose')) or mk('describe the problem with one local number and its source')}</p><p>{mk('why this area, why now')}</p>
<h2>4. What we will do</h2><p>{mk('the activities, in plain steps')}</p><table><tr><th>When</th><th>Milestone</th></tr>{ms}</table>
<h2>5. Who benefits</h2><p>{f'{int(ben["total"] or 0):,} people are already enrolled in this project ({gtxt}).' if ben['total'] else mk('number and kind of people, how they are chosen')} {mk('villages or wards')}</p>
<h2>6. Expected results and how we will measure them</h2><table><tr><th>Result</th><th>Who</th><th class="n">Target</th><th>How we will check</th></tr>{res}</table>
<h2>7. Budget</h2><table><tr><th>Head</th><th class="n">Amount</th></tr>{bud}</table><p class="sm">{('Project budget on record: ' + inr(budget) + '. ') if budget else ''}Costs are estimates from our own records and quotations. {mk('attach quotations')}</p>
<h2>8. Monitoring and reporting to you</h2><p>We will send a progress report every quarter with figures, photographs (only with consent) and a short story, a utilisation certificate signed by our chartered accountant, and invite your team to visit at any time. Our records are kept in a register of activities, attendance and spending, and are open to your auditors.</p>
<h2>9. Sustainability</h2><p>{mk('how the work continues after the grant: local ownership, government schemes, other funders')}</p>
<h2>10. Our credentials</h2><table>{idr}</table><h2>11. Governing body</h2><table><tr><th>Name</th><th>Role</th></tr>{tr}</table>
<h2>12. Documents we will attach</h2><ul>{dl}</ul>
{('<h2>13. Additional notes</h2><p>' + esc(notes) + '</p>') if notes else ''}
<h2>Contact</h2><p>{esc(o.get('head') or '')} {mk('name and designation')}, {esc(o.get('phone'))}, {esc(o.get('email'))}</p>
<div class="sig"><div>{esc(o.get('head') or 'Authorised signatory')}</div><div>Date</div></div>
<div class="draft noprint">Draft made from your own records on {today.isoformat()}. Yellow brackets are for you to fill in. Replace every bracket, check each figure and the Schedule VII wording, and use the company's own format if it has one. Ask your CA and trustees to read it before it goes out.</div>"""
    page = PAGE.replace("</style>", "mark{{background:#fff3a3}}</style>", 1)
    return page.format(title=esc("CSR proposal " + p["name"]), body=body).encode(), f"csr-proposal-{(p.get('code') or p['id'])}.html"
