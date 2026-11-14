"""CSR / funder report builder: one self-contained page for a project and a period, made from your own records.
It is a DRAFT for you to read and edit before it is sent. Photos shown are only those with consent."""
import base64, datetime, html as _h
from . import logic, db, media, journey
from .compliance_pack import PAGE, _head, inr

class CsrError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg); self.status, self.msg = status, msg

def esc(x): return _h.escape(str(x if x is not None else ""))
def _dt(x, lab):
    try: return datetime.date.fromisoformat(x)
    except (TypeError, ValueError): raise CsrError(400, f"{lab}: use a date like 2026-04-01")

def _photo(m):
    for rel in (m["thumb"], m["file"]):
        if not rel: continue
        try:
            fp = media.abspath(rel)
            with open(fp, "rb") as fh: raw = fh.read(600_000 + 1)
            if len(raw) > 600_000: continue
            mime = "image/png" if raw[:4] == b"\x89PNG" else "image/jpeg"
            return f"data:{mime};base64," + base64.b64encode(raw).decode()
        except (OSError, media.MediaError): continue
    return None

def gather(c, project_id, a, b):
    p = logic.one(c, "SELECT * FROM projects WHERE id=:i", dict(i=project_id))
    if not p: raise CsrError(404, "Project not found")
    A, B = _dt(a, "From"), _dt(b, "To")
    if B < A: raise CsrError(400, "The end date is before the start date")
    if (B - A).days > 800: raise CsrError(400, "Choose a period of at most about two years")
    P = dict(p=project_id, a=a, b=b)
    act = logic.one(c, "SELECT COUNT(*) n, COALESCE(SUM(people_reached),0) people, COALESCE(SUM(volunteers),0) vol, COALESCE(SUM(spent),0) spent FROM activities WHERE project_id=:p AND date BETWEEN :a AND :b", P)
    kinds = logic.rows(c, "SELECT COALESCE(NULLIF(activity,''),'Other') activity, COUNT(*) n, SUM(people_reached) people FROM activities WHERE project_id=:p AND date BETWEEN :a AND :b GROUP BY 1 ORDER BY n DESC", P)
    months = logic.rows(c, "SELECT substr(date,1,7) month, COUNT(*) n, SUM(people_reached) people, SUM(spent) spent FROM activities WHERE project_id=:p AND date BETWEEN :a AND :b GROUP BY 1 ORDER BY 1", P)
    villages = [r["village"] for r in c.execute("SELECT DISTINCT village FROM activities WHERE project_id=? AND date BETWEEN ? AND ? AND COALESCE(village,'')<>'' ORDER BY village", (project_id, a, b))]
    ben = logic.one(c, "SELECT COUNT(*) total, SUM(date_joined BETWEEN :a AND :b) new_in_period FROM beneficiaries WHERE project_id=:p", P)
    gender = logic.rows(c, "SELECT COALESCE(NULLIF(gender,''),'Not recorded') k, COUNT(*) n FROM beneficiaries WHERE project_id=:p GROUP BY 1 ORDER BY n DESC", P)
    ages = logic.rows(c, "SELECT COALESCE(NULLIF(age_group,''),'Not recorded') k, COUNT(*) n FROM beneficiaries WHERE project_id=:p GROUP BY 1 ORDER BY n DESC", P)
    results = logic.rows(c, "SELECT * FROM results WHERE project_id=:p ORDER BY id", P)
    heads = logic.rows(c, "SELECT * FROM project_spend WHERE project_id=:p ORDER BY id", P)
    grants = logic.rows(c, "SELECT g.id, g.code, g.funder, g.sanctioned, (SELECT COALESCE(SUM(amount),0) FROM instalments WHERE grant_id=g.id) recd, (SELECT COALESCE(SUM(amount),0) FROM grant_spend WHERE grant_id=g.id) used FROM grants g WHERE g.project_id=:p", P)
    photos = logic.rows(c, """SELECT id, caption, file, thumb FROM media WHERE project_id=:p AND kind='photo' AND consent='Y' AND purpose='event'
                              AND substr(COALESCE(NULLIF(taken_at,''), created),1,10) BETWEEN :a AND :b ORDER BY id DESC LIMIT 6""", P)
    jr = journey.summary(c, project_id)
    return dict(p=p, a=a, b=b, act=act, kinds=kinds, months=months, villages=villages, ben=ben, gender=gender, ages=ages, results=results,
                heads=heads, grants=grants, photos=photos, journey=jr)

def report(c, project_id, a, b, notes=""):
    g = gather(c, project_id, a, b); p = g["p"]; o = logic.org_info(db.get_settings(c))
    people = int(g["act"]["people"] or 0); spent = float(g["act"]["spent"] or 0)
    per = f"{inr(spent / people)}" if people else "n/a"
    res = "".join(f"<tr><td>{esc(r['result'])}</td><td>{esc(r['people_group'])}</td><td class='n'>{r['target']:g} {esc(r['unit'])}</td><td class='n'>{r['achieved']:g}</td><td class='n'>{(r['achieved'] / r['target'] * 100 if r['target'] else 0):.0f}%</td></tr>" for r in g["results"]) or "<tr><td colspan='5'>No results entered yet (Programme → Results).</td></tr>"
    hd = "".join(f"<tr><td>{esc(r['head'])}</td><td class='n'>{inr(r['budget'])}</td><td class='n'>{inr(r['used'])}</td><td class='n'>{inr((r['budget'] or 0) - (r['used'] or 0))}</td></tr>" for r in g["heads"]) or "<tr><td colspan='4'>No spending heads entered for this project.</td></tr>"
    gr = "".join(f"<tr><td>{esc(x['code'])} · {esc(x['funder'])}</td><td class='n'>{inr(x['sanctioned'])}</td><td class='n'>{inr(x['recd'])}</td><td class='n'>{inr(x['used'])}</td><td class='n'>{inr(x['recd'] - x['used'])}</td></tr>" for x in g["grants"]) or "<tr><td colspan='5'>No grant linked to this project.</td></tr>"
    kinds = "".join(f"<tr><td>{esc(k['activity'])}</td><td class='n'>{k['n']}</td><td class='n'>{int(k['people'] or 0):,}</td></tr>" for k in g["kinds"]) or "<tr><td colspan='3'>No activities logged in this period.</td></tr>"
    mon = "".join(f"<tr><td>{esc(m['month'])}</td><td class='n'>{m['n']}</td><td class='n'>{int(m['people'] or 0):,}</td><td class='n'>{inr(m['spent'])}</td></tr>" for m in g["months"])
    fn = "".join(f"<tr><td>{esc(f['stage'])}</td><td class='n'>{f['count']}</td></tr>" for f in g["journey"]["funnel"]) if g["journey"]["total"] else ""
    outs = "".join(f"<li>{esc(x['outcome'])} ({x['n']})</li>" for x in g["journey"]["outcomes"])
    imgs = "".join(f"<figure style='display:inline-block;margin:4px;width:31%;vertical-align:top'><img style='width:100%' src='{u}' alt=''><figcaption class='sm'>{esc(m['caption'])}</figcaption></figure>" for m in g["photos"] for u in [_photo(m)] if u)
    story = "".join(f"<p><b>{lab}:</b> {esc(p[k])}</p>" for k, lab in (("story_person", "Who"), ("story_before", "Before"), ("story_did", "What we did"), ("story_after", "After"), ("story_quote", "In their words"), ("story_next", "What next")) if p.get(k))
    pcts = (f"{spent / p['budget'] * 100:.0f}% of the project budget" if p.get("budget") else "")
    body = _head(o) + f"""<h2 style="text-align:center;font-size:18px">Project report: {esc(p['name'])}</h2><p class="sm" style="text-align:center">Reporting period {esc(g['a'])} to {esc(g['b'])}</p>
<table><tr><th>Project</th><td>{esc(p['name'])} {('(' + esc(p['code']) + ')') if p.get('code') else ''}</td><th>Place</th><td>{esc(p['place'])}</td></tr>
<tr><th>Funder</th><td>{esc(p['funder'])}</td><th>Stage</th><td>{esc(p['stage'])}</td></tr>
<tr><th>Project dates</th><td>{esc(p['start'])} to {esc(p['end'])}</td><th>Lead</th><td>{esc(p['lead'])}</td></tr></table>
{('<h2>Purpose</h2><p>' + esc(p['purpose']) + '</p>') if p.get('purpose') else ''}
<h2>At a glance</h2><table><tr><th>Activities held</th><th>People reached</th><th>Volunteers</th><th>Spent on activities</th><th>Cost per person reached</th></tr>
<tr><td class="n">{g['act']['n']}</td><td class="n">{people:,}</td><td class="n">{int(g['act']['vol'] or 0):,}</td><td class="n">{inr(spent)}</td><td class="n">{per}</td></tr></table>
<p class="sm">{('Villages covered: ' + esc(', '.join(g['villages'])) + '. ') if g['villages'] else ''}{esc(pcts)}</p>
<h2>Targets and results</h2><table><tr><th>Result</th><th>People group</th><th class="n">Target</th><th class="n">Achieved</th><th class="n">Done</th></tr>{res}</table>
<h2>Work done in this period</h2><table><tr><th>Kind of activity</th><th class="n">Times</th><th class="n">People reached</th></tr>{kinds}</table>
{('<table><tr><th>Month</th><th class="n">Activities</th><th class="n">People</th><th class="n">Spent</th></tr>' + mon + '</table>') if mon else ''}
<h2>People served</h2><p>{g['ben']['total'] or 0} people are enrolled in this project; {int(g['ben']['new_in_period'] or 0)} joined in this period.</p>
<table><tr><th>Gender</th><th class="n">People</th></tr>{''.join(f"<tr><td>{esc(x['k'])}</td><td class='n'>{x['n']}</td></tr>" for x in g['gender']) or '<tr><td colspan="2">None enrolled</td></tr>'}</table>
<table><tr><th>Age group</th><th class="n">People</th></tr>{''.join(f"<tr><td>{esc(x['k'])}</td><td class='n'>{x['n']}</td></tr>" for x in g['ages']) or '<tr><td colspan="2">None enrolled</td></tr>'}</table>
{('<h2>Journey of the people served</h2><p class="sm">How many people reached each step.</p><table><tr><th>Step</th><th class="n">People</th></tr>' + fn + '</table>' + (('<p>Outcomes recorded:</p><ul>' + outs + '</ul>') if outs else '')) if fn else ''}
<h2>Money: budget and use</h2><table><tr><th>Head</th><th class="n">Budget</th><th class="n">Used</th><th class="n">Balance</th></tr>{hd}</table>
<table><tr><th>Grant</th><th class="n">Sanctioned</th><th class="n">Received</th><th class="n">Used</th><th class="n">Unspent</th></tr>{gr}</table>
{('<h2>A story from the field</h2>' + story) if story else ''}
{('<h2>Photos</h2>' + imgs + '<p class="sm">Only photos with the person\'s consent are shown.</p>') if imgs else ''}
{('<h2>Notes</h2><p>' + esc(notes) + '</p>') if notes else ''}
<div class="sig"><div>{esc(o.get('head') or 'Authorised signatory')}</div><div>Date</div></div>
<div class="draft noprint">Draft made from your own records on {datetime.date.today().isoformat()}. Read every number, add your own notes, and check it against your funder's format before sending. Financial figures are working figures; your CA certifies the accounts.</div>"""
    return PAGE.format(title=esc("Project report " + p["name"]), body=body).encode(), f"project-report-{(p.get('code') or p['id'])}-{a}-{b}.html"
