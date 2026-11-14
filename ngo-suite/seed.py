#!/usr/bin/env python3
"""Load demo data modelled on the NGO & Trust toolkit samples. Safe to run once on an empty database.
Usage: python3 seed.py   (creates users admin/accounts/field/viewer, password 'ChangeMe123')"""
import os, sys, random, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import db, server, v13, v14

def main():
    db.init_db(); c = db.connect()
    if c.execute("SELECT 1 FROM donors").fetchone():
        print("Database already has data; not seeding."); return
    rnd = random.Random(7)
    today = datetime.date.today()
    D = lambda n: (today - datetime.timedelta(days=n)).isoformat()
    F = lambda n: (today + datetime.timedelta(days=n)).isoformat()
    S = dict(org_name="Seva Sankalp Trust", org_head="Kavita Sharma", org_address="12 Gandhi Nagar, Your City", org_phone="+91 98290 61234",
             org_email="sevasankalp@example.com", org_reg="12A, 80G, FCRA (sample - check with your CA)", org_tagline="Working for education, skills and care",
             org_upi="sevasankalp@upi", reporting_period="April to November 2026", prepared_by="Sunita Meena", designation="Programme Coordinator",
             funds_available="1500000", reserve_pct="0.1", running_cost_month="70000", months_to_keep="3", central_office_cost="180000",
             camp_people="300", camp_days="2", camp_venue="6000", camp_kit_per_person="40", camp_food_per_person_day="35", camp_other="8000", camp_sponsor="20000",
             cash_opening="250000", reserve_to_build="200000", limit_per_person="2500")
    for k, v in S.items(): c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, v))
    for kind, vals in dict(city=["Your City", "Near Town A", "Near Town B", "Village C"], village=["Rampura", "Lakhanpur", "Sundarpur", "Devgaon", "Khera", "Ward 7"],
        purpose=["Village School Support", "Women Skill Centre", "Health Camp Series", "Tree Plantation Drive", "Elder Care Visits"]).items():
        for v in vals: c.execute("INSERT OR IGNORE INTO lists(kind,value) VALUES(?,?)", (kind, v))
    for un, nm, role in (("admin", "Administrator", "admin"), ("accounts", "Accounts Officer", "accountant"), ("field", "Field Coordinator", "programme"), ("viewer", "Trustee (view only)", "viewer")):
        h, salt = db.hash_pw("ChangeMe123")
        c.execute("INSERT OR REPLACE INTO users(username,name,role,pw_hash,salt,must_change) VALUES(?,?,?,?,?,0)", (un, nm, role, h, salt))
    admin = dict(username="admin")
    mk = lambda t, d: server.create(c, t, d, admin)

    funds = {}
    for n, t, p, o in (("General Fund", "General", "Running cost", 180000), ("Education Fund", "Restricted", "Village School and Scholarship", 90000),
                       ("Skill Centre Fund", "Restricted", "Women Skill Centre", 60000), ("Health Fund", "Restricted", "Health camps", 40000),
                       ("Corpus Fund", "Corpus", "Kept as capital", 500000)):
        funds[n] = mk("funds", dict(name=n, type=t, purpose=p, opening=o))

    P = {}
    projdata = [
     ("Village School Support", "Rampura", "Kavita", -210, 150, 240, 400000, "Running", "Asha Education Fund", "Restricted", 12, 300000, 0.30, "Help village children stay in school and learn well",
      ("Pooja, 13", "Pooja left school in Class 6 to care for her brothers while her parents worked.", "Our field worker met her parents four times and gave her a cycle.", "Pooja is back in Class 7 and attends every day.", "I thought school was over for me. Now I go by cycle with my friends.", "94", "children back in class", "Next we will start two more after-school classes.")),
     ("Women Skill Centre", "Sanganer", "Meena", -150, 215, 60, 350000, "Running", "City Industries Trust", "Restricted", 12, 280000, 0.25, "Six-month tailoring training for women at home", None),
     ("Health Camp Series", "Alwar", "Dr. Rohit", -100, 80, 900, 120000, "Running", "General Donors", "General", 6, 90000, 0.15, "Free check-up camps in villages far from a clinic",
      ("Kamla Devi, 58", "Kamla Devi had not seen a doctor in six years because the nearest clinic was far away.", "A camp came to her village; she was checked and our volunteers explained her medicine.", "She now goes for follow-up visits.", "They came to our village. I did not have to ask anyone for money.", "1,120", "people checked in camps", "Next we will hold the last three camps in the hill villages.")),
     ("Tree Plantation Drive", "Tonk", "Imran", -20, 100, 1200, 70000, "Started", "Green Earth Fund", "Restricted", 4, 60000, 0.10, "Plant and protect saplings on village common land", None),
     ("Elder Care Visits", "Bundi", "Sunita", -300, -5, 80, 80000, "Reporting", "General Donors", "General", 12, 70000, 0.12, "Weekly home visits for elders living alone", None),
     ("Scholarship Support", "Jaipur", "Anil", 10, 280, 35, 130000, "Approved", "Member Donations", "General", 10, 120000, 0.08, "Scholarships for students from poor families", None)]
    for n, pl, lead, s0, e0, tgt, bud, stg, fu, ft, mo, pr, sh, purpose, st in projdata:
        d = dict(name=n, place=pl, lead=lead, start=D(-s0) if s0 > 0 else D(-s0), end=F(e0) if e0 > 0 else D(-e0), target_people=tgt, budget=bud, stage=stg,
                 funder=fu, fund_type=ft, months=mo, funds_promised=pr, my_share_pct=sh, purpose=purpose)
        d["start"] = D(-s0) if s0 < 0 else F(s0)
        if st: d.update(dict(zip(("story_person", "story_before", "story_did", "story_after", "story_quote", "story_number", "story_number_meaning", "story_next"), st)))
        P[n] = mk("projects", d)
    # budget lines
    BL = {"Village School Support": [("Teacher honorarium", "Staff", 4, 7000, 12), ("Books and uniforms", "Programme", 240, 750, 1), ("Cycles and kits", "Programme", 100, 2100, 1), ("Parent meetings", "Programme", 24, 1667, 1), ("Office and accounts", "Admin", 1, 3000, 12)],
          "Women Skill Centre": [("Trainer fee", "Staff", 2, 12000, 12), ("Sewing machines", "Programme", 20, 8500, 1), ("Raw material", "Programme", 60, 1500, 1), ("Centre rent", "Admin", 1, 6000, 12)],
          "Health Camp Series": [("Doctor honorarium", "Staff", 12, 4000, 1), ("Medicines", "Programme", 900, 60, 1), ("Camp venue and food", "Programme", 12, 3500, 1), ("Appeal printing", "Fundraising", 1, 5000, 1)],
          "Tree Plantation Drive": [("Saplings", "Programme", 1200, 35, 1), ("Guards and tools", "Programme", 1, 12000, 1), ("Field staff", "Staff", 1, 4000, 4)],
          "Elder Care Visits": [("Visitor travel", "Programme", 12, 1500, 1), ("Ration kits", "Programme", 80, 420, 1), ("Coordinator", "Staff", 1, 2500, 12)],
          "Scholarship Support": [("Scholarship grants", "Programme", 35, 2800, 1), ("Verification visits", "Admin", 1, 6000, 1), ("Donor events", "Fundraising", 1, 8000, 1)]}
    for pn, ls in BL.items():
        for ln, g, q, u, t in ls: mk("budget_lines", dict(project_id=P[pn], line=ln, grp=g, qty=q, unit_cost=u, times=t))
    # results and money for donor report
    RES = {"Village School Support": [("Girls back in school", "girls", 120, 94, "Girls"), ("Cycles given to girls", "cycles", 60, 52, ""), ("After-school classes held", "classes", 200, 168, ""), ("Parent meetings held", "meetings", 24, 21, "")],
           "Women Skill Centre": [("Women trained", "women", 60, 58, "Women"), ("Batches finished", "batches", 3, 2, ""), ("Women earning after training", "women", 40, 14, "")],
           "Health Camp Series": [("People checked in camps", "people", 900, 1120, "Villagers"), ("Camps held", "camps", 12, 9, ""), ("Referrals followed up", "people", 150, 60, "")],
           "Tree Plantation Drive": [("Saplings planted", "saplings", 1200, 400, ""), ("Saplings alive after 3 months", "saplings", 1000, 180, "")],
           "Elder Care Visits": [("Elders visited weekly", "elders", 80, 76, "Elders"), ("Ration kits given", "kits", 80, 80, "")]}
    for pn, rs in RES.items():
        for r, u, t, a, g in rs: mk("results", dict(project_id=P[pn], result=r, unit=u, target=t, achieved=a, people_group=g))
    SP = {"Village School Support": [("Teacher honorarium", 420000, 236000), ("Books and uniforms", 180000, 128000), ("Cycles and kits", 210000, 182000), ("Parent meetings", 40000, 22500)],
          "Women Skill Centre": [("Training", 200000, 150000), ("Material", 120000, 96000), ("Admin costs", 30000, 21000)],
          "Health Camp Series": [("Camp supplies", 80000, 71000), ("Staff salaries", 30000, 25000), ("Travel", 10000, 9200)],
          "Tree Plantation Drive": [("Material", 50000, 40000), ("Staff salaries", 20000, 6000)],
          "Elder Care Visits": [("Food and ration", 40000, 39000), ("Travel", 24000, 21000), ("Staff salaries", 30000, 29500)]}
    for pn, hs in SP.items():
        for h, b, u in hs: mk("project_spend", dict(project_id=P[pn], head=h, budget=b, used=u))

    # donors + donations
    names = ["City Traders", "Asha Rao", "Mohan Lal & Sons", "Priya Jain", "Green Earth Fund", "Rotary Club", "Dr. Verma", "Sanjay Gupta", "Neha Agarwal", "Harish Agarwal",
             "Lions Club", "Ravi Textiles", "Suman Devi", "Kiran Sethi", "Jai Hind Trust", "Anil Kapoor", "Meera Nair", "Faizal Khan", "Gopal Das", "Ritu Singh"]
    dtypes = ["Company", "Individual", "Company", "Individual", "Trust or Group", "Trust or Group", "Individual", "Member", "Member", "Individual", "Trust or Group", "Company", "Individual", "Member", "Trust or Group", "Individual", "Member", "Individual", "Individual", "Individual"]
    cities = ["Your City", "Near Town A", "Near Town B", "Village C"]
    donors = []
    for i, n in enumerate(names):
        nf = D(-rnd.randint(-10, 5)) if i % 4 == 0 else None
        bd = today if i == 1 else today + datetime.timedelta(days=3) if i == 4 else (datetime.date(1960 + rnd.randint(0, 40), rnd.randint(1, 12), rnd.randint(1, 28)) if i % 2 == 0 else None)
        if i in (1, 4): bd = bd.replace(year=1985)
        donors.append(mk("donors", dict(name=n, email=f"donor{i}@example.org", birthday=bd.isoformat() if bd else None, wishes="N" if i == 6 else "Y", phone=f"+91 98{rnd.randint(10000000, 99999999)}", city=rnd.choice(cities), donor_type=dtypes[i],
                                        next_followup=(today + datetime.timedelta(days=rnd.randint(-3, 3))).isoformat() if i % 3 == 0 else None)))
    purposes = [("General Donation", "General", "General Fund"), ("Village School Support", "Restricted", "Education Fund"), ("Women Skill Centre", "Restricted", "Skill Centre Fund"),
                ("Health Camp Series", "Restricted", "Health Fund"), ("Corpus Gift", "Corpus", "Corpus Fund")]
    modes = ["UPI", "Bank transfer", "Cheque", "Cash"]
    for k in range(70):
        p = purposes[rnd.choices(range(5), [4, 3, 2, 2, 1])[0]]
        d = today - datetime.timedelta(days=rnd.randint(0, 300))
        mk("donations", dict(date=d.isoformat(), donor_id=rnd.choice(donors), purpose=p[0], fund_type=p[1], mode=rnd.choice(modes), reference=f"REF{5100 + k}",
                             amount=rnd.choice([500, 1000, 2000, 2500, 5000, 10000, 15000, 25000, 50000]), fund_id=funds[p[2]],
                             receipt_given="Y" if k % 9 else "N", thank_you_sent="Y" if k % 7 else "N"))
    # beneficiaries, activities
    first = ["Mohan", "Sita", "Raju", "Geeta", "Ramesh", "Lata", "Vijay", "Anita", "Kamal", "Sunita", "Deepak", "Pooja", "Arjun", "Rekha", "Sunil", "Kavya"]
    last = ["Sharma", "Meena", "Gurjar", "Yadav", "Verma", "Bairwa", "Khan", "Saini"]
    vill = ["Rampura", "Lakhanpur", "Sundarpur", "Devgaon", "Khera", "Ward 7"]
    svc = {"Village School Support": ("Class support", ["Child"]), "Women Skill Centre": ("Skill training", ["Youth", "Adult"]), "Health Camp Series": ("Health camp", ["Adult", "Elder", "Child"]),
           "Tree Plantation Drive": ("Saplings", ["Adult"]), "Elder Care Visits": ("Home visit", ["Elder"]), "Scholarship Support": ("Scholarship", ["Youth"])}
    for k in range(120):
        pn = rnd.choice(list(svc)); sv, ages = svc[pn]
        g = "Female" if pn == "Women Skill Centre" else rnd.choice(["Female", "Male", "Female"])
        mk("beneficiaries", dict(date_joined=D(rnd.randint(5, 200)), name=f"{rnd.choice(first)} {rnd.choice(last)}", phone=f"+91 94{rnd.randint(10000000, 99999999)}", village=rnd.choice(vill),
                                 gender=g, age_group=rnd.choice(ages), project_id=P[pn], service=sv, status=rnd.choice(["Active"] * 5 + ["Completed", "Dropped"])))
    acts = {"Village School Support": ("Class", 35, 1500), "Women Skill Centre": ("Training", 20, 4000), "Health Camp Series": ("Camp", 150, 9000),
            "Tree Plantation Drive": ("Field visit", 60, 3500), "Elder Care Visits": ("Home visit", 25, 1200), "Scholarship Support": ("Distribution", 12, 6000)}
    for k in range(60):
        pn = rnd.choice(list(acts)); a, pp, sp = acts[pn]
        mk("activities", dict(date=D(rnd.randint(2, 200)), project_id=P[pn], activity=a, village=rnd.choice(vill), people_reached=int(pp * rnd.uniform(.6, 1.4)),
                              volunteers=rnd.randint(1, 5), spent=round(sp * rnd.uniform(.7, 1.3), -1)))
    # team, attendance, volunteers
    staff = [("Kavita Sharma", "Project Coordinator", "Monthly", 22000), ("Meena Joshi", "Trainer", "Monthly", 15000), ("Anil Verma", "Accountant", "Monthly", 18000),
             ("Sunita Meena", "Field Worker", "Per day", 600), ("Imran Khan", "Field Worker", "Per day", 550), ("Rohit Saini", "Teacher", "Per day", 700),
             ("Geeta Yadav", "Office Helper", "Monthly", 9000), ("Deepak Bairwa", "Field Worker", "Per day", 500)]
    tid = [mk("team", dict(name=n, role=r, pay_type=pt, pay_rate=rate, phone=f"+91 98{rnd.randint(10000000, 99999999)}", active="Y")) for n, r, pt, rate in staff]
    vols = [mk("team", dict(name=f"{rnd.choice(first)} {rnd.choice(last)}", role="Volunteer", pay_type="Volunteer", pay_rate=0, active="Y")) for _ in range(12)]
    pm = today - datetime.timedelta(days=7)
    months = [(pm.year, pm.month)]
    prev = datetime.date(pm.year, pm.month, 1) - datetime.timedelta(days=1); months.append((prev.year, prev.month))
    for (y, m) in months:
        for day in range(1, 29):
            dt = datetime.date(y, m, day)
            if dt.weekday() == 6 or dt > today: continue
            for t in tid:
                att = rnd.choices(["P", "A", "H", "L"], [85, 4, 6, 5])[0]
                mk("attendance", dict(date=dt.isoformat(), team_id=t, attendance=att, extra_hours=rnd.choice([0, 0, 0, 1, 2]) if att == "P" else 0,
                                      advance_paid=3000 if day == 10 and t == tid[3] else 0))
        for _ in range(25):
            dt = datetime.date(y, m, rnd.randint(1, 28))
            if dt <= today: mk("volunteer_log", dict(date=dt.isoformat(), team_id=rnd.choice(vols), duty=rnd.choice(["Health camp", "Class help", "Tree planting", "Home visit"]),
                                                     hours=rnd.choice([3, 4, 5, 6]), km=rnd.choice([0, 8, 12, 20]), other_paid=rnd.choice([0, 0, 50, 100])))
    # grants
    G = {}
    for fu, pn, s0, e0, san, rep in (("Asha Education Fund", "Village School Support", -210, 150, 300000, 25), ("City Industries Trust", "Women Skill Centre", -150, 215, 280000, 60),
                                     ("Green Earth Fund", "Tree Plantation Drive", -20, 100, 60000, 70), ("Health For All Foundation", "Health Camp Series", -100, 80, 150000, 12),
                                     ("Old Age Care Society", "Elder Care Visits", -300, -5, 70000, -3)):
        G[fu] = mk("grants", dict(funder=fu, project_id=P[pn], start=(today + datetime.timedelta(days=s0)).isoformat(), end=(today + datetime.timedelta(days=e0)).isoformat(),
                                  sanctioned=san, report_due=F(rep)))
    ins = {"Asha Education Fund": [(-200, 150000, "Education Fund"), (-90, 100000, "Education Fund")], "City Industries Trust": [(-140, 140000, "Skill Centre Fund")],
           "Green Earth Fund": [(-15, 30000, None)], "Health For All Foundation": [(-95, 100000, "Health Fund")], "Old Age Care Society": [(-290, 70000, "General Fund")]}
    for fu, rows in ins.items():
        for i, (d, a, f) in enumerate(rows): mk("instalments", dict(date=D(-d), grant_id=G[fu], reference=f"INS-{300 + i}", amount=a, fund_id=funds[f] if f else None))
    sp = {"Asha Education Fund": [("Salaries", 90000, "Education Fund"), ("Material", 70000, "Education Fund"), ("Events", 12000, "Education Fund")], "City Industries Trust": [("Training", 90000, "Skill Centre Fund"), ("Material", 40000, "Skill Centre Fund")],
          "Green Earth Fund": [("Material", 20000, None)], "Health For All Foundation": [("Material", 60000, "Health Fund"), ("Travel", 15000, "Health Fund")], "Old Age Care Society": [("Salaries", 30000, "General Fund"), ("Material", 38000, "General Fund")]}
    n = 4000
    for fu, rows in sp.items():
        for h, a, f in rows:
            n += 1; mk("grant_spend", dict(date=D(rnd.randint(5, 150)), grant_id=G[fu], head=h, voucher_no=f"V-{n}", paid_to=rnd.choice(["Staff", "Local supplier", "Printing press", "Transport"]),
                                           amount=a, bill_kept="N" if n == 4003 else "Y", fund_id=funds[f] if f else None))
    # other cash book entries
    for i in range(36):
        d = today - datetime.timedelta(days=rnd.randint(0, 250))
        if i % 6 == 0: mk("cash_book", dict(date=d.isoformat(), type="Receipt", fund_id=funds["General Fund"], head="Interest", party="Bank", mode="Bank transfer", amount=rnd.choice([2200, 3100, 4500])))
        else:
            h = rnd.choice(["Salaries", "Rent", "Office", "Travel", "Fundraising", "CA and accounts", "Programme"])
            mk("cash_book", dict(date=d.isoformat(), type="Payment", fund_id=funds["General Fund"], head=h, party=rnd.choice(["Landlord", "Staff", "Stationer", "CA firm"]), mode=rnd.choice(["Bank transfer", "UPI", "Cash"]),
                                 amount=round(rnd.choice([3000, 6000, 12000, 18000, 24000, 9000]) * rnd.uniform(.8, 1.2), -1)))
    for nme, cost, raised in (("Annual dinner", 40000, 260000), ("Online appeal", 6000, 85000), ("Door-to-door drive", 15000, 70000), ("School fete stall", 5000, 22000)):
        mk("appeals", dict(name=nme, cost=cost, raised=raised))
    cm = today.strftime("%Y-%m")
    for i in range(1, 13):
        ym = server.logic.month_add(cm, i - 1)
        mk("cashflow_plan", dict(month=ym, expected_in=[120000, 90000, 80000, 350000, 100000, 90000, 150000, 80000, 95000, 300000, 90000, 110000][i - 1], expected_out=[110000, 115000, 100000, 120000, 125000, 105000, 110000, 150000, 120000, 115000, 125000, 140000][i - 1]))
    # records for documents
    r1 = mk("records", dict(date=D(40), party="Asha Education Fund", phone="+91 98860 31977", address="Sector 2, Your City", project="Village School Support", purpose="Education Fund", period_ref="2026-27", people=240, amount=5000, received=2500))
    for it, dt, q, u, t, rt in (("Books and material", "Village School Support", 1, "nos", 1, 2500), ("Uniforms", "Village School Support", 10, "set", 1, 250)):
        mk("record_lines", dict(record_id=r1, item=it, detail=dt, qty=q, unit=u, times=t, rate=rt))
    r2 = mk("records", dict(date=D(10), party="Trustees", project="Women Skill Centre", purpose="Quarterly meeting", period_ref="Q2", people=7, amount=0, received=0, next_date=F(20)))
    for it in ("Review of accounts", "Skill centre batch 3", "Fundraising plan"):
        mk("record_lines", dict(record_id=r2, item=it, qty=1, times=1, rate=0))
    for k, (dn, ch, out, summ, nf) in enumerate((
            (2, "Call", "Promised gift", "Spoke about the school fete. Said they will give after Diwali.", F(3)), (3, "Visit", "Reached", "Visited the shop; shared the annual report.", F(20)),
            (5, "WhatsApp", "No answer", "Sent the appeal message; no reply yet.", D(2)), (7, "Call", "Needs follow-up", "Asked for a statement of last year's gifts.", F(0)),
            (8, "Email", "Reached", "Sent thank-you and photos from the health camp.", ""))):
        mk("interactions", dict(date=D(6 - k), donor_id=donors[dn], channel=ch, direction="Out", summary=summ, outcome=out, next_followup=nf, owner="Field Coordinator"))
    for nm, ph, em, rel, tg in (("Ravi Meena", "+91 98290 11001", "ravi@example.org", "Volunteer", "Volunteers"), ("Sunita Rathore", "+91 98290 11002", "", "Volunteer", "Volunteers, Health camp"),
                                ("Mr. Gupta (Block officer)", "+91 98290 11003", "", "Official", "Officials"), ("Daily Herald reporter", "+91 98290 11004", "news@example.org", "Media", "Media"),
                                ("Dr. Verma (Camp doctor)", "+91 98290 11005", "", "Partner", "Health camp")):
        mk("contacts", dict(name=nm, phone=ph, email=em, relation=rel, tags=tg, city="Your City", msg_optin="Y", wishes="Y"))
    for t, dd, rp, rm in (("Quarterly TDS payment (sample - check dates with your CA)", F(9), "Quarterly", 10), ("Annual accounts to auditor (sample)", F(45), "Yearly", 30),
                          ("Insurance renewal (sample)", D(3), "Yearly", 20), ("Trustee meeting", F(25), "Quarterly", 7)):
        mk("compliance", dict(title=t, due_date=dd, repeat=rp, remind_days=rm))
    if os.environ.get("NGO_SEED_SAMPLE", "1") != "0":
        # ---- v9 sample data: a worked example donor, company partners, funder payments, decisions, reply inbox (all made up)
        asha = mk("donors", dict(name="Asha Verma", email="asha.sample@example.com", phone="+91 98000 00001", city="Near Town A", donor_type="Individual", wishes="Y",
                                 owner="Sunita Meena", backup_owner="Anil Verma", handover_note="Prefers WhatsApp in Marathi. Likes school-visit photos. (sample)"))
        mk("commitments", dict(donor_id=asha, amount=5000, frequency="Monthly", start=D(150), purpose="General Donation", status="Active", notes="UPI standing instruction (sample)"))
        for k in range(5):
            mk("donations", dict(date=D(150 - 30 * k), donor_id=asha, purpose="General Donation", fund_type="General", mode="UPI", reference=f"ASHA{k + 1}",
                                 amount=5000, fund_id=funds["General Fund"], receipt_given="Y", thank_you_sent="Y"))
        mk("interactions", dict(date=D(3), donor_id=asha, channel="WhatsApp", direction="In", summary="Asked if she can sponsor a child's schooling (sample).", outcome="Needs follow-up", next_followup=F(2), owner="Sunita Meena"))
        cp = {}
        for nm, sec, stg, foc, ct, amt, ren, nxt, nd in (
                ("Sunrise Tech Pvt Ltd (sample)", "IT", "Proposal", "Education", "Rahul Mehta", 300000, F(120), "Send revised budget for the school lab", F(6)),
                ("Bright Foods Ltd (sample)", "Food", "Active", "Health", "Neeta Rao", 150000, F(28), "Thank them and share the camp photos", F(4)),
                ("Metro Steel (sample)", "Manufacturing", "Pitched", "Skills", "Vikram Shah", 500000, "", "Call HR head to fix a meeting", F(10)),
                ("City Bank Branch (sample)", "Banking", "Renewal due", "Education", "Anjali Singh", 200000, F(15), "Send last year's impact report", D(2))):
            cp[nm] = mk("partners", dict(name=nm, sector=sec, stage=stg, csr_focus=foc, contact_name=ct, contact_email="contact@example.com", expected_amount=amt,
                                          renewal_date=ren or None, last_contact=D(9), next_step=nxt, next_step_date=nd, owner="Kavita Sharma", backup_owner="Sunita Meena" if stg != "Pitched" else None,
                                          handover_note="Meets only on weekday mornings (sample)" if stg == "Active" else None))
        bf = cp["Bright Foods Ltd (sample)"]
        mk("partner_events", dict(date=D(20), partner_id=bf, title="Volunteer day at the village school", kind="Volunteering", project_id=P["Village School Support"], venue="Rampura",
                                  planned_people=40, attended=36, hours=144, raised=0, status="Done", note="Painted two classrooms (sample)"))
        mk("partner_events", dict(date=F(12), partner_id=bf, title="Health camp sponsor visit", kind="Site visit", project_id=P["Health Camp Series"], venue="Alwar",
                                  planned_people=12, attended=0, hours=0, raised=0, status="Planned"))
        mk("donations", dict(date=D(30), donor_id=donors[0], purpose="Women Skill Centre", fund_type="Restricted", mode="Bank transfer", reference="BF-CSR-1", amount=75000,
                             fund_id=funds["Skill Centre Fund"], receipt_given="Y", thank_you_sent="N", partner_id=bf))
        mk("tranches", dict(grant_id=G["City Industries Trust"], due_date=D(12), amount=70000, note="Second instalment, overdue (sample)"))
        mk("tranches", dict(grant_id=G["Green Earth Fund"], due_date=F(25), amount=30000, note="Final instalment (sample)"))
        mk("decisions", dict(date=D(14), meeting="Trustee meeting", decision="Hire a second field worker for Alwar", owner="Kavita Sharma", due=D(3), status="Open", notes="Overdue example (sample)"))
        mk("decisions", dict(date=D(14), meeting="Trustee meeting", decision="Approve revised budget for Women Skill Centre", owner="Anil Verma", due=F(15), status="Open"))
        from app import inbox as _ib
        _ib.receive(c, dict(), [
            dict(phone="+91 98000 00001", text="Please send my receipt for this month", name="Asha Verma", id="demo-1", channel="whatsapp"),
            dict(phone="+91 98000 00001", text="Can I sponsor a child?", name="Asha Verma", id="demo-2", channel="whatsapp"),
            dict(phone="+91 98290 11001", text="Yes, I will come on Saturday", name="Ravi Meena", id="demo-3", channel="whatsapp"),
            dict(phone="+91 98290 11002", text="Stop", name="Sunita Rathore", id="demo-4", channel="sms")])
        c.execute("INSERT OR REPLACE INTO inbox_threads(channel,phone,assignee,status) VALUES('whatsapp','919800000001','Sunita Meena','Open')")
        # more sample rows so every page has something to look at
        for nm, ph, am, msg, stt in (("Rekha Joshi (sample)", "+91 98000 00011", 2000, "Happy to support the school. Please call me.", "New"),
                                     ("Imran Ali (sample)", "+91 98000 00012", 10000, "Monthly sponsor for a scholarship, please send details.", "New"),
                                     ("Mahesh Traders (sample)", "+91 98000 00013", 5000, "Gift for the health camp.", "Converted")):
            c.execute("INSERT INTO pledges(ts,name,phone,email,amount,message,status,ip) VALUES(?,?,?,?,?,?,?,?)", (D(2) + "T10:00:00", nm, ph, "", am, msg, stt, "127.0.0.1"))
        for i, (cat, amt, desc, st) in enumerate((("Travel", 640, "Bus fare for village visits (sample)", "Pending"), ("Material", 1850, "Charts and markers for class (sample)", "Approved"),
                                                  ("Food", 920, "Tea and snacks for camp volunteers (sample)", "Paid"), ("Travel", 380, "Auto to health camp (sample)", "Pending"))):
            c.execute("INSERT INTO claims(claim_no,date,user_id,claimant,project_id,category,amount,description,status) VALUES(?,?,?,?,?,?,?,?,?)",
                      (f"CL-{2601 + i}", D(8 - i), 3, "Field Coordinator", P[["Village School Support", "Village School Support", "Health Camp Series", "Health Camp Series"][i]], cat, amt, desc, st))
        for i, (d, amt, ty, nar) in enumerate(((5, 5000, "Credit", "UPI/ASHA VERMA/ASHA1"), (12, 75000, "Credit", "NEFT BRIGHT FOODS CSR"), (9, 18000, "Debit", "SALARY NOV"),
                                               (20, 6000, "Debit", "RENT OFFICE"), (3, 2500, "Credit", "UPI/CITY TRADERS"))):
            c.execute("INSERT INTO bank_txns(hash,date,amount,type,narration,ref,imported) VALUES(?,?,?,?,?,?,?)", (f"demo{i}", D(d), amt, ty, nar, f"BK{9000 + i}", D(1)))
        cid = c.execute("INSERT INTO campaigns(ts,name,channel,segment,subject,body,total,sent,failed,status,user) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (D(10) + "T11:00:00", "Diwali greetings (sample)", "whatsapp", "All donors", "", "Wishing you a bright Diwali from Seva Sankalp Trust.", 5, 5, 0, "Done", "Administrator")).lastrowid
        for i, dn in enumerate(donors[:5]):
            c.execute("INSERT INTO messages(campaign_id,kind,rid,name,to_addr,channel,status,ts) VALUES(?,?,?,?,?,?,?,?)", (cid, "donor", dn, names[i], f"+91 98000 0010{i}", "whatsapp", "sent", D(10) + "T11:00:05"))
        bens = [r[0] for r in c.execute("SELECT id FROM beneficiaries ORDER BY id LIMIT 3")]
        for bi, b in enumerate(bens):
            for j, (stg, det, outc) in enumerate((("Enrolled", "Joined after a home visit", ""), ("Service started", "First class attended", ""), ("Follow-up visit", "Checked progress with family", "Attending regularly"))):
                c.execute("INSERT INTO journey(beneficiary_id,date,stage,detail,outcome,recorded_by) VALUES(?,?,?,?,?,?)", (b, D(90 - 30 * j - bi), stg, det, outc, "Field Coordinator"))
        try:
            from app import cards as _cards
            mk_month = today.strftime("%Y-%m")
            _cards.create(c, dict(username="admin", name="Administrator"), dict(project_id=P["Village School Support"], month=mk_month, story="Sample card: Pooja is back in Class 7 and attends every day."))
        except Exception as e:
            print("Impact card sample skipped:", e)
        for i, (k, to, sub) in enumerate((("thank-you", "asha.sample@example.com", "Thank you for your gift (sample)"), ("receipt", "asha.sample@example.com", "Your receipt R-2026-0412 (sample)"))):
            c.execute("INSERT INTO email_log(ts,kind,tbl,row_id,year,to_addr,subject,status) VALUES(?,?,?,?,?,?,?,?)", (D(5) + "T09:00:00", k, "donations", 1 + i, today.year, to, sub, "sent"))
        # sample photos (made-up pictures), logo, and a duplicate donor pair so those pages show something
        try:
            import base64, sample_assets
            from app import media as _media, comms as _comms
            pm = {"school": "Village School Support", "health": "Health Camp Series", "trees": "Tree Plantation Drive", "skills": "Women Skill Centre", "elder": "Elder Care Visits", "team": "Health Camp Series"}
            acts_by_proj = {r[1]: r[0] for r in c.execute("SELECT id, project_id FROM activities ORDER BY id DESC")}
            for i, (k, v) in enumerate(sample_assets.PHOTOS.items()):
                rel, fp = _media._newpath("jpg"); trel, tfp = _media._newpath("jpg", ".t")
                open(fp, "wb").write(base64.b64decode(v["photo"])); open(tfp, "wb").write(base64.b64decode(v["thumb"]))
                c.execute("INSERT INTO media(kind,purpose,file,thumb,mime,size,project_id,activity_id,caption,consent,taken_at,uploaded_by,uploader,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          ("photo", "event", rel, trel, "image/jpeg", os.path.getsize(fp), P[pm[k]], acts_by_proj.get(P[pm[k]]), v["caption"] + " (sample)", "Y", D(5 + i * 3), 3, "Field Coordinator", D(5 + i * 3) + "T12:00:00"))
            _comms.save_logo(c, "data:image/png;base64," + sample_assets.LOGO_PNG)
        except Exception as e:
            print("Sample photos skipped:", e)
        mk("donors", dict(name="Ashaa Verma", phone="+91 98000 00001", email="asha.sample@example.com", city="Near Town A", donor_type="Individual", notes="Sample duplicate of Asha Verma"))
        mk("donors", dict(name="Mohan Lal and Sons", phone="+91 98111 22233", city="Your City", donor_type="Company", notes="Sample duplicate of Mohan Lal & Sons"))
        # v10 samples: outcomes, legacy pipeline, risks, incidents, event people, donor page, public pages
        for t, cost, per, pn, ds in (("Keeps one girl in school for a year", 2500, "year", "Village School Support", "Books, uniform and a mentor visit"),
                                     ("Trains one woman in tailoring", 6000, "one-time", "Women Skill Centre", "Six months of training and a starter kit"),
                                     ("Runs one health camp check-up day", 9000, "one-time", "Health Camp Series", "Doctor, medicines and volunteers for one day"),
                                     ("Plants and protects 50 saplings", 1750, "one-time", "Tree Plantation Drive", "Saplings, tree guards and three months of care")):
            mk("outcomes", dict(title=t + " (sample)", unit_cost=cost, per=per, project_id=P[pn], description=ds, active="Y"))
        mk("legacies", dict(donor_id=donors[1], stage="Talked to family", expected=500000, last_contact=D(20), next_contact=F(14), owner="Kavita Sharma", notes="Mentioned the trust in her will (sample)"))
        mk("legacies", dict(name="Dr. S. Kulkarni (sample)", stage="Interested", expected=200000, last_contact=D(45), next_contact=F(30), owner="Sunita Meena", notes="Asked how to leave a gift"))
        mk("legacies", dict(donor_id=donors[6], stage="Confirmed in writing", expected=1000000, last_contact=D(70), next_contact=F(90), owner="Kavita Sharma"))
        for t, cat, l, i, own, mit, st in (("Loss of the main funder this year", "Money", 3, 5, "Kavita Sharma", "Three funders in talks; six months of reserve kept (sample)", "Open"),
                                           ("Key person leaves without handover", "People", 4, 4, "", "", "Open"),
                                           ("Child safeguarding concern in a project", "Safety", 2, 5, "Anil Verma", "Policy, training for field staff, reporting form", "Watching"),
                                           ("Late filing of returns", "Legal and compliance", 2, 4, "Anil Verma", "Calendar reminders; CA reviews every quarter", "Open"),
                                           ("Data on phones is lost or leaked", "Technology", 3, 3, "Imran Khan", "Weekly backup; password on every phone", "Open")):
            mk("risks", dict(title=t + " (sample)", category=cat, likelihood=str(l), impact=str(i), owner=own, mitigation=mit, status=st, review_date=F(30) if own else D(10)))
        for nm, rl, yrs in (("Dr. Meera Iyer (sample)", "Chairperson", 2400), ("Anil Verma (sample)", "Secretary", 2400), ("Kavita Sharma (sample)", "Treasurer", 1800), ("R. K. Joshi (sample)", "Trustee", 900)):
            mk("trustees", dict(name=nm, role=rl, since=D(yrs), status="Active"))
        for nm, kd, ad, rv, sg in (("Safeguarding and child protection", "Safeguarding", D(200), F(165), "Yes"), ("Finance, procurement and travel", "Finance", D(400), D(20), "Partly"),
                                   ("Conflict of interest and code of conduct", "Governance", D(300), F(65), "Yes"), ("Prevention of sexual harassment (POSH)", "People", None, None, "No"),
                                   ("Data protection and privacy", "Data and privacy", None, None, "No")):
            mk("policies", dict(name=nm + " (sample)", kind=kd, adopted_on=ad or "", next_review=rv or "", owner="Anil Verma", staff_signed=sg))
        mk("meetings", dict(date=D(60), kind="Board or trustees", place="Office", attendees="Four of four trustees (sample)", quorum="Y", agenda="Budget, grant report, new project", minutes="Budget approved; grant report to go by month end (sample).", next_date=F(30)))
        mk("meetings", dict(date=D(250), kind="AGM", place="Office", attendees="All members (sample)", quorum="Y", agenda="Accounts, audit report, election of trustees", minutes="Accounts adopted (sample).", next_date=F(115)))
        _m = c.execute("SELECT id FROM media WHERE consent='Y' ORDER BY id LIMIT 1").fetchone(); _mid = _m["id"] if _m else None
        mk("social_posts", dict(title="Skill centre batch certificates (sample)", platform="Instagram", plan_date=D(12), project_id=P["Village School Support"], media_id=_mid, caption="Twenty women finished their stitching course this month. Thank you to everyone who stood with them. (sample)", status="Posted", owner="Imran Khan", approved_by="Kavita Sharma", posted_on=D(12), reach=1840, reactions=212, gifts_amount=7500))
        mk("social_posts", dict(title="Health camp this Saturday (sample)", platform="Facebook", plan_date=F(5), project_id=P["Health Camp Series"], caption="Free health camp this Saturday, 9 am to 1 pm. Please share. (sample)", status="Approved", owner="Imran Khan", approved_by="Anil Verma"))
        mk("social_posts", dict(title="Thank you, volunteers (sample)", platform="WhatsApp channel", plan_date=F(2), caption="", status="Idea", owner="Imran Khan"))
        v13.add_standard_plan(c)
        v14.add_standard_docs(c)
        c.execute("UPDATE official_docs SET status='Have', number='(sample number)', issued_on=?, valid_until=? WHERE name LIKE '12A%'", (D(900), F(120)))
        c.execute("UPDATE official_docs SET status='Have', number='(sample number)', issued_on=?, valid_until=? WHERE name LIKE '80G%'", (D(700), F(40)))
        c.execute("UPDATE official_docs SET status='Applied', notes='Applied on the MCA portal (sample)' WHERE name LIKE 'CSR-1%'")
        for co, kd, st, foc, ask, san, nd, ns, ow in (("Sunrise Tech Pvt Ltd (sample)", "CSR grant", "Pitched", "Education", 600000, 0, F(40), "Send revised budget", "Kavita Sharma"),
                                                     ("Bright Foods (sample)", "CSR grant", "Disbursing", "Nutrition", 300000, 300000, F(20), "Quarterly report", "Anil Verma"),
                                                     ("Cisco-style tech firm (sample)", "Matching gift", "Approached", "Health", 0, 0, F(10), "Ask HR for the matching form", "Imran Khan"),
                                                     ("Local steel works (sample)", "CSR grant", "Target", "Skills", 250000, 0, F(15), "Find the CSR head", "Sunita Meena"),
                                                     ("Metro Bank (sample)", "Volunteering", "Plan approval", "Women's livelihood", 450000, 0, F(75), "Follow up after board", "Kavita Sharma")):
            mk("csr_pipeline", dict(company=co, kind=kd, stage=st, focus=foc, ask=ask, sanctioned=san, next_date=nd, next_step=ns, owner=ow, decision_by=F(60) if st in ("Pitched", "Plan approval") else ""))
        mk("incidents", dict(date=D(45), kind="Complaint", project_id=P["Village School Support"], people="Parent, Rampura", description="A parent complained that a class started late (sample).", action_taken="Spoke to teacher; timetable fixed", reported_to="Programme lead", owner="Kavita Sharma", status="Open"))
        mk("incidents", dict(date=D(8), kind="Accident or injury", project_id=P["Health Camp Series"], people="Volunteer (initials R.M.)", description="Minor cut at the camp, first aid given (sample).", action_taken="First aid; kit restocked", reported_to="Trustee", owner="Dr. Rohit", status="Closed", closed_on=D(7)))
        ev3 = mk("partner_events", dict(date=D(6), partner_id=cp["Sunrise Tech Pvt Ltd (sample)"], title="Book donation drive", kind="Collection drive", project_id=P["Village School Support"], venue="Sunrise Tech office", planned_people=8, attended=0, hours=0, raised=0, status="Done", note="Collected 240 books (sample)"))
        for nm, hrs, role in (("Rahul Mehta", 3, "Team lead"), ("Priyanka Rao", 2.5, "Sorting"), ("Amit Shah", 2.5, "Packing"), ("Divya Nair", 3, "Registration"), ("Karan Patel", 2, "Transport")):
            mk("event_people", dict(event_id=ev3, name=nm, hours=hrs, role=role))
        c.execute("UPDATE donors SET portal_token='demo-giving-page-asha-1' WHERE id=?", (asha,))
        for k, v in (("public_transparency", "Yes"), ("transparency_note", "We publish how we use your money. These figures are from our own records (sample)."), ("donate_page", "Yes"),
                     ("donate_message", "Every rupee goes to the work you choose (sample page).")):
            c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, v))
    c.commit(); c.close()
    print("Demo data loaded. Users: admin, accounts, field, viewer  (password: ChangeMe123)")

if __name__ == "__main__":
    main()
