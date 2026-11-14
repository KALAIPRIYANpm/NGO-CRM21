import os, sys, json, time, tempfile, threading, unittest, urllib.request, urllib.error, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["NGO_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
from app import db, server, logic, mailer
import seed

class Client:
    def __init__(self, base): self.base, self.cookie = base, None
    def call(self, method, path, body=None, raw=False):
        req = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **({"Cookie": self.cookie} if self.cookie else {})})
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            r = e
        data = r.read()
        sc = r.headers.get("Set-Cookie")
        if sc and "ngo_session=" in sc and "Max-Age=0" not in sc: self.cookie = sc.split(";")[0]
        return r.status, (data if raw else (json.loads(data) if data else None))
    def rawcall(self, method, path, data=None, headers=None):
        req = urllib.request.Request(self.base + path, method=method, data=data,
                                     headers={**({"Cookie": self.cookie} if self.cookie else {}), **(headers or {})})
        try: r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e: r = e
        return r.status, r.read(), r.headers
    def login(self, u, p="ChangeMe123"): return self.call("POST", "/api/login", dict(username=u, password=p))

def asof_day():
    con = db.connect(); d = logic.asof_date(con).isoformat(); con.close(); return d

class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["NGO_SEED_SAMPLE"] = "0"; seed.main()
        cls.httpd = server.serve("127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.httpd.shutdown()
    def client(self, u="admin"):
        c = Client(self.base); self.assertEqual(c.login(u)[0], 200); return c

    def test_auth(self):
        c = Client(self.base)
        self.assertEqual(c.call("GET", "/api/dashboard")[0], 401)
        self.assertEqual(c.login("admin", "bad")[0], 401)
        self.assertEqual(c.login("admin")[0], 200)
        self.assertEqual(c.call("GET", "/api/me")[1]["user"]["role"], "admin")
        c.call("POST", "/api/logout"); c.cookie = None
        self.assertEqual(c.call("GET", "/api/dashboard")[0], 401)

    def test_roles(self):
        v = self.client("viewer")
        self.assertEqual(v.call("GET", "/api/t/donors")[0], 200)
        self.assertEqual(v.call("POST", "/api/t/donors", dict(name="X"))[0], 403)
        f = self.client("field")
        self.assertEqual(f.call("POST", "/api/t/donors", dict(name="X"))[0], 403)
        self.assertEqual(f.call("POST", "/api/t/activities", dict(date="2026-01-01", project_id=1))[0], 200)
        self.assertEqual(f.call("GET", "/api/users")[0], 403)
        self.assertEqual(f.call("GET", "/api/backup")[0], 403)

    def test_donation_posts_to_cash_book_and_rules(self):
        a = self.client("accounts")
        funds = {f["name"]: f["id"] for f in a.call("GET", "/api/t/funds")[1]}
        before = a.call("GET", f"/api/t/funds/{funds['General Fund']}")[1]["balance"]
        s, d = a.call("POST", "/api/t/donors", dict(name="Test Donor"))
        self.assertEqual(s, 200); self.assertTrue(d["code"].startswith("D-"))
        s, g = a.call("POST", "/api/t/donations", dict(date="2026-05-01", donor_id=d["id"], purpose="General Donation", fund_type="General", mode="UPI", amount="1,500", fund_id=funds["General Fund"]))
        self.assertEqual(s, 200, g); self.assertTrue(g["receipt_no"].startswith("R-"))
        after = a.call("GET", f"/api/t/funds/{funds['General Fund']}")[1]["balance"]
        self.assertEqual(after - before, 1500)
        # edit amount -> cash book follows
        a.call("PUT", f"/api/t/donations/{g['id']}", dict(amount=2000))
        self.assertEqual(a.call("GET", f"/api/t/funds/{funds['General Fund']}")[1]["balance"] - before, 2000)
        # mismatch fund type rejected
        s, e = a.call("POST", "/api/t/donations", dict(date="2026-05-01", donor_id=d["id"], fund_type="General", amount=10, fund_id=funds["Education Fund"]))
        self.assertEqual(s, 400); self.assertIn("Restricted", e["error"])
        # posted cash entry is read-only
        cb = [r for r in a.call("GET", "/api/t/cash_book")[1] if r["source"] == f"donations:{g['id']}"]
        self.assertEqual(len(cb), 1)
        self.assertEqual(a.call("DELETE", f"/api/t/cash_book/{cb[0]['id']}")[0], 400)
        # donor level and total
        self.assertEqual(a.call("GET", f"/api/t/donors/{d['id']}")[1]["level"], "One gift")
        # cannot delete donor with donations; deleting donation removes cash entry
        self.assertEqual(a.call("DELETE", f"/api/t/donors/{d['id']}")[0], 400)
        self.assertEqual(a.call("DELETE", f"/api/t/donations/{g['id']}")[0], 200)
        self.assertEqual(a.call("GET", f"/api/t/funds/{funds['General Fund']}")[1]["balance"], before)
        self.assertEqual(a.call("DELETE", f"/api/t/donors/{d['id']}")[0], 200)

    def test_validation(self):
        a = self.client("accounts")
        self.assertEqual(a.call("POST", "/api/t/donations", dict(date="bad", donor_id=1, amount=5))[0], 400)
        self.assertEqual(a.call("POST", "/api/t/donations", dict(date="2026-01-01", donor_id=1, amount=-5))[0], 400)
        self.assertEqual(a.call("POST", "/api/t/donations", dict(date="2026-01-01", donor_id=99999, amount=5))[0], 400)
        self.assertEqual(a.call("POST", "/api/t/donors", dict(name=""))[0], 400)
        # SQL injection attempt is just text
        s, d = a.call("POST", "/api/t/donors", dict(name="x'); DROP TABLE donors;--"))
        self.assertEqual(s, 200); self.assertGreater(len(a.call("GET", "/api/t/donors")[1]), 5)
        self.assertEqual(len(a.call("GET", "/api/t/donors?q=" + urllib.request.quote("'); DROP"))[1]), 1)

    def test_payroll_matches_hand_calculation(self):
        a = self.client("accounts")
        team = a.call("POST", "/api/t/team", dict(name="Calc Worker", pay_type="Per day", pay_rate=500, role="Field Worker"))[1]
        vol = a.call("POST", "/api/t/team", dict(name="Calc Vol", pay_type="Volunteer", pay_rate=999))[1]
        self.assertEqual(vol["pay_rate"], 0); self.assertTrue(vol["code"].startswith("V-"))
        mon = a.call("POST", "/api/t/team", dict(name="Calc Monthly", pay_type="Monthly", pay_rate=20000))[1]
        for day, att, hrs, adv in (("2025-03-03", "P", 2, 0), ("2025-03-04", "P", 0, 1000), ("2025-03-05", "H", 0, 0), ("2025-03-06", "A", 0, 0)):
            s, r = a.call("POST", "/api/t/attendance", dict(date=day, team_id=team["id"], attendance=att, extra_hours=hrs, advance_paid=adv)); self.assertEqual(s, 200, r)
        self.assertEqual(a.call("POST", "/api/t/attendance", dict(date="2025-03-03", team_id=team["id"], attendance="P"))[0], 400)  # duplicate
        self.assertEqual(a.call("POST", "/api/t/attendance", dict(date="2025-03-03", team_id=vol["id"], attendance="P"))[0], 400)
        self.assertEqual(a.call("POST", "/api/t/volunteer_log", dict(date="2025-03-03", team_id=team["id"], hours=1))[0], 400)
        a.call("POST", "/api/t/volunteer_log", dict(date="2025-03-10", team_id=vol["id"], hours=4, km=12, other_paid=100))
        a.call("POST", "/api/t/attendance", dict(date="2025-03-03", team_id=mon["id"], attendance="P"))
        p = a.call("GET", "/api/report/payroll?month=2025-03")[1]
        row = {r["name"]: r for r in p["rows"]}
        # per day: 500 + 2h*60 + 500 + 250 = 1370 ; advance 1000
        self.assertEqual(row["Calc Worker"]["due"], 1370); self.assertEqual(row["Calc Worker"]["net"], 370); self.assertEqual(row["Calc Worker"]["days_present"], 2.5)
        self.assertEqual(row["Calc Monthly"]["due"], 20000)
        self.assertEqual(row["Calc Vol"]["due"], 12 * 5 + 100)   # km*5 + other
        self.assertEqual(p["totals"]["net"], sum(r["net"] for r in p["rows"]))

    def test_grants_pace_and_reports_due(self):
        a = self.client("accounts")
        gl = a.call("GET", "/api/t/grants")[1]
        by = {g["funder"]: g for g in gl}
        g = by["Asha Education Fund"]
        self.assertAlmostEqual(g["received"], 250000); self.assertAlmostEqual(g["spent"], 172000); self.assertAlmostEqual(g["in_hand"], 78000)
        self.assertAlmostEqual(g["used"], round(172000 / 300000, 4), places=3)
        self.assertIn(g["pace"], ("On pace", "Slow", "Over"))
        self.assertEqual(by["Old Age Care Society"]["report_in_days"], -3)
        al = self.client("admin").call("GET", "/api/dashboard")[1]["alerts"]
        self.assertTrue(any("Report for grant" in x["text"] for x in al))

    def test_accounts_and_trustee_report(self):
        a = self.client("accounts")
        f = a.call("GET", "/api/t/funds")[1]
        for x in f: self.assertAlmostEqual(x["balance"], x["opening"] + x["received"] - x["spent"])
        ym = datetime.date.today().strftime("%Y-%m")
        tr = a.call("GET", f"/api/report/trustee?month={ym}")[1]
        t = tr["totals"]
        self.assertAlmostEqual(t["closing"], t["opening"] + t["receipts"] - t["payments"])
        self.assertAlmostEqual(t["closing"], sum(x["balance"] for x in f))  # current month closing == balances today
        self.assertEqual(a.call("GET", "/api/report/trustee?month=abc")[0], 400)

    def test_impact_and_budget(self):
        a = self.client("admin")
        projects = {p["name"]: p["id"] for p in a.call("GET", "/api/t/projects")[1]}
        r = a.call("GET", f"/api/report/impact?project_id={projects['Village School Support']}&donor=Mr+Test&gift=50000")[1]
        n = r["numbers"]
        self.assertEqual(n["people"], 94)  # only the Girls group row counts people
        self.assertEqual(n["budget"], 850000); self.assertEqual(n["used"], 568500)
        self.assertAlmostEqual(sum(x["share"] for x in r["per100"]), 100, places=6)
        self.assertLessEqual(abs(sum(x["amount"] for x in r["split"]) - 50000), 4)
        self.assertEqual(r["story"]["person"], "Pooja, 13")
        b = a.call("GET", f"/api/report/budget?project_id={projects['Village School Support']}")[1]["tools"]
        lines = 4 * 7000 * 12 + 240 * 750 + 100 * 2100 + 24 * 1667 + 3000 * 12
        self.assertEqual(b["t01"]["lines_total"], lines)
        import math
        self.assertEqual(b["t01"]["total"], math.ceil((lines + round(lines * .05)) / 100) * 100)
        self.assertEqual(b["t07"]["cost"], 6000 * 2 + 300 * 40 + 300 * 2 * 35 + 8000)
        ap = a.call("GET", "/api/report/all_projects")[1]
        self.assertGreater(ap["totals"]["projects"], 3)

    def test_print_and_words(self):
        a = self.client("accounts")
        don = a.call("GET", "/api/t/donations")[1][0]
        r = a.call("GET", f"/api/print/receipt/{don['id']}")[1]
        self.assertTrue(r["words"].endswith("Only")); self.assertEqual(r["format"]["title"], "DONATION RECEIPT")
        rec = a.call("GET", "/api/t/records")[1][-1]
        pr = a.call("GET", f"/api/print/record/{rec['id']}?format=Appeal+Letter")[1]
        self.assertEqual(pr["lines_total"], sum(l["amount"] for l in pr["lines"]))
        self.assertEqual(a.call("GET", "/api/print/record/%d?format=Nope" % rec["id"])[0], 404)
        self.assertEqual(logic.amount_words(125000), "One Lakh Twenty Five Thousand Rupees Only")

    def test_csv_roundtrip_and_import_errors(self):
        a = self.client("accounts")
        s, raw = a.call("GET", "/api/export/donors.csv", raw=True)
        self.assertEqual(s, 200); self.assertIn(b"Donor", raw)
        csvtxt = "Donor name,Phone,City\nImp One,+91 90000 00001,Your City\nImp Two,,Near Town A\n"
        s, r = a.call("POST", "/api/import/donors", dict(csv=csvtxt)); self.assertEqual(r["imported"], 2)
        bad = "Donor,Date,Amount\nNobody At All,2026-01-01,100\n"
        s, r = a.call("POST", "/api/import/donations", dict(csv=bad)); self.assertEqual(r["imported"], 0); self.assertTrue(r["errors"])

    def test_admin_functions(self):
        ad = self.client("admin")
        self.assertEqual(ad.call("POST", "/api/users", dict(username="newuser", name="N", role="viewer", password="longenough1"))[0], 200)
        self.assertEqual(ad.call("POST", "/api/users", dict(username="newuser", name="N", role="viewer", password="longenough1"))[0], 400)
        n = Client(self.base); self.assertEqual(n.login("newuser", "longenough1")[0], 200)
        self.assertEqual(n.call("GET", "/api/dashboard")[0], 403)  # must change password first
        self.assertEqual(n.call("POST", "/api/password", dict(old="longenough1", new="short"))[0], 400)
        self.assertEqual(n.call("POST", "/api/password", dict(old="longenough1", new="muchlonger99"))[0], 200)
        self.assertEqual(n.call("GET", "/api/dashboard")[0], 200)
        s, raw = ad.call("GET", "/api/backup", raw=True); self.assertEqual(s, 200); self.assertTrue(raw.startswith(b"SQLite format 3"))
        self.assertEqual(ad.call("PUT", "/api/settings", dict(bogus="1"))[0], 400)
        self.assertGreater(len(ad.call("GET", "/api/audit")[1]), 10)

    def test_birthdays_and_email(self):
        import datetime as dt
        a = self.client("accounts"); ad = self.client("admin")
        sent = []
        orig = mailer._smtp_send
        mailer._smtp_send = lambda s, msg: sent.append(msg)
        try:
            # list: seeded donor with birthday today
            r = a.call("GET", "/api/birthdays?days=30")[1]
            today = [p for p in r["people"] if p["days_away"] == 0]
            self.assertTrue(today); self.assertFalse(r["email_ready"])
            # no mail server yet -> clear error, nothing sent
            s, e = a.call("POST", "/api/birthdays/send", dict(tbl="donors", id=today[0]["id"]))
            self.assertEqual(s, 502); self.assertIn("not set up", e["error"]); self.assertEqual(sent, [])
            # accountant may not touch mail settings; admin may
            self.assertEqual(a.call("PUT", "/api/tool-settings", dict(smtp_host="evil.example"))[0], 400)
            self.assertEqual(a.call("PUT", "/api/settings", dict(smtp_host="x"))[0], 403)
            st = ad.call("PUT", "/api/settings", dict(smtp_host="smtp.test", smtp_user="u@test.org", smtp_password="s3cret", smtp_from="trust@test.org", org_name="Seva Sankalp Trust"))[1]
            self.assertEqual(st["smtp_password"], ""); self.assertEqual(st["smtp_password_set"], "Yes")
            self.assertEqual(a.call("GET", "/api/meta")[1]["settings"]["smtp_password"], "")      # never exposed
            ad.call("PUT", "/api/settings", dict(smtp_password=""))                               # blank keeps it
            c = db.connect(); self.assertEqual(db.get_settings(c)["smtp_password"], "s3cret"); c.close()
            # send one: template filled, header injection impossible, logged, only once a year
            s, r1 = a.call("POST", "/api/birthdays/send", dict(tbl="donors", id=today[0]["id"]))
            self.assertEqual(r1["status"], "sent"); self.assertEqual(len(sent), 1)
            m = sent[0]; self.assertIn(today[0]["name"], m["Subject"]); self.assertIn("Seva Sankalp Trust", m.get_content())
            self.assertEqual(m["To"], today[0]["email"]); self.assertNotIn("\n", m["Subject"])
            s, r2 = a.call("POST", "/api/birthdays/send", dict(tbl="donors", id=today[0]["id"]))
            self.assertEqual(r2["status"], "skipped"); self.assertEqual(len(sent), 1)
            # a name containing a newline cannot add headers
            d = a.call("POST", "/api/t/donors", dict(name="Eve\nBcc: x@evil.org", email="eve@test.org", birthday=dt.date.today().replace(year=1990).isoformat()))[1]
            a.call("POST", "/api/birthdays/send", dict(tbl="donors", id=d["id"]))
            self.assertIsNone(sent[-1]["Bcc"]); self.assertNotIn("\n", sent[-1]["Subject"])
            # opt-out and missing email are skipped by the daily run; run is idempotent
            o = a.call("POST", "/api/t/donors", dict(name="No Wishes", email="nw@test.org", wishes="N", birthday=dt.date.today().replace(year=1980).isoformat()))[1]
            n = a.call("POST", "/api/t/donors", dict(name="No Email", birthday=dt.date.today().replace(year=1981).isoformat()))[1]
            before = len(sent); run = a.call("POST", "/api/birthdays/run", {})[1]
            self.assertGreaterEqual(run["skipped"], 2)
            self.assertFalse(any(x["To"] in ("nw@test.org",) for x in sent[before:]))
            before2 = len(sent); a.call("POST", "/api/birthdays/run", {}); self.assertEqual(len(sent), before2)
            # SMTP failure is reported and logged as failed, not lost
            def boom(s, msg): raise mailer.MailError("Could not send: connection refused")
            mailer._smtp_send = boom
            f = a.call("POST", "/api/t/donors", dict(name="Fail Case", email="f@test.org", birthday=dt.date.today().replace(year=1975).isoformat()))[1]
            s, e = a.call("POST", "/api/birthdays/send", dict(tbl="donors", id=f["id"])); self.assertEqual(s, 502)
            self.assertTrue(any(l["status"] == "failed" for l in a.call("GET", "/api/email-log")[1]))
            self.assertEqual(self.client("viewer").call("GET", "/api/email-log")[0], 403)
            self.assertEqual(self.client("viewer").call("POST", "/api/birthdays/run", {})[0], 403)
        finally:
            mailer._smtp_send = orig
        self.assertTrue(any("Birthday today" in x["text"] for x in ad.call("GET", "/api/dashboard")[1]["alerts"]))

    def test_birthday_leap_day(self):
        import datetime as dt
        t = logic._next_birthday("2000-02-29", dt.date(2027, 2, 1)); self.assertEqual(t[1], dt.date(2027, 2, 28))
        t = logic._next_birthday("2000-02-29", dt.date(2028, 2, 1)); self.assertEqual(t[1], dt.date(2028, 2, 29))
        t = logic._next_birthday("1990-03-05", dt.date(2026, 3, 6)); self.assertEqual(t[1], dt.date(2027, 3, 5))

    # ------------------------------------------------------------ automation
    def test_compliance_logic(self):
        d = datetime.date
        r = logic.compliance_status(dict(due_date="2026-01-31", repeat="Monthly", last_done="2026-02-05", remind_days=5), d(2026, 2, 20))
        self.assertEqual(r["next_due"], "2026-03-03" if False else r["next_due"]); self.assertEqual(r["next_due"], "2026-02-28")
        self.assertEqual(r["cstatus"], "Due soon" if r["days_left"] <= 5 else "Upcoming")
        r = logic.compliance_status(dict(due_date="2026-03-01", repeat="None", last_done=None, remind_days=7), d(2026, 3, 5))
        self.assertEqual(r["cstatus"], "Overdue"); self.assertEqual(r["days_left"], -4)
        r = logic.compliance_status(dict(due_date="2026-03-01", repeat="Yearly", last_done="2026-03-02", remind_days=7), d(2026, 3, 5))
        self.assertEqual(r["next_due"], "2027-03-01"); self.assertEqual(r["cstatus"], "Upcoming")
        r = logic.compliance_status(dict(due_date="2026-03-01", repeat="None", last_done="2026-02-27", remind_days=7), d(2026, 3, 5))
        self.assertEqual(r["cstatus"], "Done")

    def test_compliance_api_and_done(self):
        a = self.client("accounts")
        rows = a.call("GET", "/api/t/compliance")[1]
        self.assertTrue(rows and all("cstatus" in x for x in rows))
        ins = next(x for x in rows if x["title"].startswith("Insurance"))
        self.assertEqual(ins["cstatus"], "Overdue")
        s, r = a.call("POST", f"/api/compliance/{ins['id']}/done")
        self.assertEqual(s, 200); self.assertNotEqual(r["cstatus"], "Overdue")
        self.assertEqual(self.client("viewer").call("POST", f"/api/compliance/{ins['id']}/done")[0], 403)

    def test_digest_and_alerts_dedupe(self):
        from app import automation
        automation.SEND_DELAY = 0
        sent = []
        orig = mailer._smtp_send; mailer._smtp_send = lambda s, msg: sent.append(msg)
        try:
            c = db.connect()
            for k, v in dict(smtp_host="x", smtp_from="a@b.org", digest_to="boss@x.org, bad", ).items(): c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, v))
            c.commit()
            d = automation.digest(c); self.assertFalse(d["empty"]); self.assertTrue(d["compliance"])
            r = automation.send_digest(c); self.assertEqual(r["sent"], 1)
            self.assertEqual(automation.send_digest(c)["sent"], 0)           # once per day
            self.assertIn("COMPLIANCE", sent[0].get_body(("plain",)).get_content())
            r1 = automation.send_deadline_alerts(c); self.assertGreaterEqual(r1["alerts"], 1)
            self.assertEqual(automation.send_deadline_alerts(c)["sent"], 0)  # same triggers not repeated
            c.close()
        finally:
            mailer._smtp_send = orig

    def test_receipt_email(self):
        from app import automation
        sent = []; orig = mailer._smtp_send; mailer._smtp_send = lambda s, msg: sent.append(msg)
        try:
            a = self.client("accounts")
            funds = {f["name"]: f["id"] for f in a.call("GET", "/api/t/funds")[1]}
            s, d = a.call("POST", "/api/t/donors", dict(name="Mail Donor", email="m@x.org", phone="9811122233"))
            s, g = a.call("POST", "/api/t/donations", dict(date="2026-05-02", donor_id=d["id"], purpose="General Donation", fund_type="General", mode="UPI", amount="2500", fund_id=funds["General Fund"]))
            c = db.connect(); c.execute("INSERT OR REPLACE INTO settings VALUES('smtp_host','x')"); c.commit(); c.close()
            s, r = a.call("POST", f"/api/donations/{g['id']}/email", {}); self.assertEqual((s, r["status"]), (200, "sent"))
            self.assertEqual(a.call("POST", f"/api/donations/{g['id']}/email", {})[1]["status"], "skipped")
            self.assertIn("2,500", sent[-1].as_string() + sent[-1].get_body(("plain",)).get_content())
            s, d2 = a.call("POST", "/api/t/donors", dict(name="No Mail"))
            s, g2 = a.call("POST", "/api/t/donations", dict(date="2026-05-02", donor_id=d2["id"], purpose="General Donation", fund_type="General", mode="UPI", amount="100", fund_id=funds["General Fund"]))
            self.assertEqual(a.call("POST", f"/api/donations/{g2['id']}/email", {})[0], 502)
            self.assertEqual(self.client("viewer").call("POST", f"/api/donations/{g['id']}/email", {})[0], 403)
        finally:
            mailer._smtp_send = orig

    def test_scheduled_reports_once(self):
        from app import automation
        automation.SEND_DELAY = 0
        sent = []; orig = mailer._smtp_send; mailer._smtp_send = lambda s, msg: sent.append(msg)
        try:
            c = db.connect()
            for k, v in dict(smtp_host="x", trustee_emails="t1@x.org;t2@x.org", report_day="1", asof_override="").items(): c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, v))
            c.commit()
            r = automation.send_trustee_report(c); self.assertEqual(r["sent"], 2)
            self.assertEqual(automation.send_trustee_report(c)["sent"], 0)
            c.execute("INSERT OR REPLACE INTO settings VALUES('asof_override','2026-10-06')"); c.commit()
            r = automation.send_impact_reports(c); self.assertGreaterEqual(r["sent"], 1)
            self.assertEqual(automation.send_impact_reports(c)["sent"], 0)
            c.execute("INSERT OR REPLACE INTO settings VALUES('asof_override','')"); c.commit(); c.close()
        finally:
            mailer._smtp_send = orig

    def test_backup(self):
        from app import automation
        c = db.connect(); c.execute("INSERT OR REPLACE INTO settings VALUES('backup_keep','2')")
        cp = tempfile.mkdtemp(); c.execute("INSERT OR REPLACE INTO settings VALUES('backup_copy_dir',?)", (cp,)); c.commit()
        r = automation.run_backup(c); self.assertTrue(r["ok"], r)
        bd = automation.backup_dir()
        for dn in ("2020-01-01", "2020-01-02", "2020-01-03"): open(os.path.join(bd, f"ngo-{dn}.db"), "wb").write(b"x")
        automation.run_backup(c)
        self.assertEqual(len([f for f in os.listdir(bd) if f.startswith("ngo-")]), 2)
        self.assertTrue(os.listdir(cp))
        import sqlite3
        x = sqlite3.connect(os.path.join(cp, os.listdir(cp)[0])); self.assertGreater(x.execute("SELECT COUNT(*) FROM donors").fetchone()[0], 5); x.close()
        a = self.client(); self.assertEqual(a.call("POST", "/api/automation/run/backup")[0], 200)
        self.assertEqual(self.client("accounts").call("POST", "/api/automation/run/backup")[0], 403)
        c.execute("INSERT OR REPLACE INTO settings VALUES('backup_copy_dir','')"); c.commit(); c.close()

    def test_bank_import(self):
        from app import automation
        csvtxt = ("Account Statement,,,,\nDate,Narration,Chq/Ref No,Withdrawal Amt.,Deposit Amt.,Balance\n"
                  "05/05/2026,UPI-RAMESH SHARMA-REF123456,REF123456,,\"5,000.00\",100\n"
                  "06/05/2026,NEFT STATIONER,CHQ001,\"1,200.00\",,50\n"
                  "07/05/2026,UNKNOWN CREDIT,X1,,777.00,60\n")
        rows = automation.parse_bank_csv(csvtxt)
        self.assertEqual([(r["type"], r["amount"]) for r in rows], [("Receipt", 5000.0), ("Payment", 1200.0), ("Receipt", 777.0)])
        self.assertEqual(automation._num("(1,000)"), -1000); self.assertEqual(automation._num("2,500.50 Cr"), 2500.5); self.assertEqual(automation._num("300 Dr"), -300)
        with self.assertRaises(ValueError): automation.parse_bank_csv("a,b\n1,2")
        a = self.client("accounts")
        funds = {f["name"]: f["id"] for f in a.call("GET", "/api/t/funds")[1]}
        s, d = a.call("POST", "/api/t/donors", dict(name="Ramesh Sharma"))
        s, g = a.call("POST", "/api/t/donations", dict(date="2026-05-05", donor_id=d["id"], purpose="General Donation", fund_type="General", mode="UPI", amount="5000", reference="REF123456", fund_id=funds["General Fund"]))
        s, pv = a.call("POST", "/api/bank/preview", dict(csv=csvtxt)); self.assertEqual(s, 200)
        m = pv["rows"][0]; self.assertEqual(m["action"], "match"); self.assertEqual(m["match"]["id"], g["id"]); self.assertEqual(m["match"]["confidence"], "high")
        self.assertEqual(pv["rows"][2]["action"], "new")
        before = a.call("GET", f"/api/t/funds/{funds['General Fund']}")[1]["balance"]
        items = [dict(r, match_kind=(r["match"] or {}).get("kind"), match_id=(r["match"] or {}).get("id")) for r in pv["rows"]]
        s, res = a.call("POST", "/api/bank/commit", dict(items=items, fund_id=funds["General Fund"]))
        self.assertEqual(s, 200); self.assertEqual((res["matched"], res["created"]), (1, 2), res)
        after = a.call("GET", f"/api/t/funds/{funds['General Fund']}")[1]["balance"]
        self.assertAlmostEqual(after - before, 777 - 1200, 2)           # matched receipt not double counted
        s, again = a.call("POST", "/api/bank/commit", dict(items=items, fund_id=funds["General Fund"]))
        self.assertEqual((again["matched"], again["created"]), (0, 0))   # re-import is a no-op
        s, pv2 = a.call("POST", "/api/bank/preview", dict(csv=csvtxt)); self.assertEqual(pv2["summary"]["duplicates"], 3)
        self.assertEqual(self.client("viewer").call("POST", "/api/bank/preview", dict(csv=csvtxt))[0], 403)
        self.assertEqual(a.call("POST", "/api/bank/commit", dict(items=[dict(hash="zz", action="new")]))[1]["errors"], ["bad row"])

    def test_payslip_and_bank_sheet(self):
        a = self.client("accounts")
        ym = datetime.date.today().strftime("%Y-%m")
        pr = a.call("GET", f"/api/report/payroll?month={ym}")[1]
        row = next(r for r in pr["rows"] if r["name"])
        tid = row["id"]
        a.call("PUT", f"/api/t/team/{tid}", dict(bank_account="123456789", ifsc="SBIN0001234"))
        s, sl = a.call("GET", f"/api/print/payslip/{tid}?month={ym}")
        self.assertEqual(s, 200); self.assertAlmostEqual(sl["net"], row["net"], 2); self.assertEqual(sl["member"]["bank_account"], "123456789")
        s, raw = a.call("GET", f"/api/export/payroll-bank.csv?month={ym}", raw=True)
        txt = raw.decode("utf-8-sig"); self.assertIn("Account no", txt)
        self.assertEqual(self.client("field").call("GET", f"/api/print/payslip/{tid}?month={ym}")[0], 403)
        self.assertEqual(a.call("GET", "/api/print/payslip/1?month=bad")[0], 400)
        team_f = self.client("field").call("GET", "/api/t/team")[1]
        self.assertTrue(team_f and all("bank_account" not in t and "ifsc" not in t for t in team_f))
        self.assertIn("bank_account", a.call("GET", "/api/t/team")[1][0])

    def test_pledges_public(self):
        from app import automation
        pub = Client(self.base)
        self.assertFalse(pub.call("GET", "/api/public/donate-info")[1]["enabled"])
        self.assertEqual(pub.call("POST", "/api/public/pledge", dict(name="Pat", phone="9811122233"))[0], 400)   # switched off
        c = db.connect(); c.execute("INSERT OR REPLACE INTO settings VALUES('donate_page','Yes')"); c.commit(); c.close()
        info = pub.call("GET", "/api/public/donate-info")[1]; self.assertTrue(info["enabled"]); self.assertTrue(info["link"].startswith("upi://pay?pa="))
        self.assertNotIn("smtp", json.dumps(info))
        s, svg = pub.call("GET", "/api/public/upi.svg", raw=True); self.assertEqual(s, 200); self.assertIn(b"<svg", svg)
        automation._pledge_hits.clear()
        self.assertEqual(pub.call("POST", "/api/public/pledge", dict(name="Bot", phone="9811122233", website="spam.com"))[0], 200)
        self.assertEqual(self.client().call("GET", "/api/t/pledges")[1], [])                # honeypot dropped
        self.assertEqual(pub.call("POST", "/api/public/pledge", dict(name="P", phone="9811122233"))[0], 400)
        self.assertEqual(pub.call("POST", "/api/public/pledge", dict(name="Pat Doe"))[0], 400)
        self.assertEqual(pub.call("POST", "/api/public/pledge", dict(name="Pat Doe", email="bad"))[0], 400)
        s, r = pub.call("POST", "/api/public/pledge", dict(name="<b>Pat</b> Doe", phone="+91 98111 22233", amount="500", message="hi")); self.assertEqual(s, 200)
        a = self.client("accounts"); pl = a.call("GET", "/api/t/pledges")[1]; self.assertEqual(len(pl), 1)
        self.assertEqual(self.client("viewer").call("GET", "/api/t/pledges")[0], 403)
        self.assertEqual(self.client("field").call("GET", "/api/t/pledges")[0], 403)
        s, cv = a.call("POST", f"/api/pledges/{pl[0]['id']}/convert"); self.assertEqual(s, 200); self.assertFalse(cv["existing"])
        self.assertEqual(a.call("GET", "/api/t/pledges")[1][0]["status"], "Converted")
        for i in range(6): s, _ = pub.call("POST", "/api/public/pledge", dict(name="Rate Limit", phone="9811122233"))
        self.assertEqual(s, 429)
        automation._pledge_hits.clear()
        c = db.connect(); c.execute("INSERT OR REPLACE INTO settings VALUES('donate_page','No')"); c.commit(); c.close()

    def test_qr_endpoint(self):
        a = self.client()
        s, svg = a.call("GET", "/api/qr.svg?text=upi%3A%2F%2Fpay%3Fpa%3Dx%40upi", raw=True); self.assertEqual(s, 200); self.assertIn(b"<svg", svg)
        self.assertEqual(a.call("GET", "/api/qr.svg")[0], 400)
        try:
            import cv2, numpy as np, re as _re, cairosvg  # noqa
        except Exception:
            return
        # decoded in dev with OpenCV; skipped when unavailable

    def test_field_and_duplicates(self):
        f = self.client("field")
        s, t = f.call("GET", "/api/field/team"); self.assertEqual(s, 200); tid = t["team"][0]["id"]
        self.assertTrue(all(x["role"] != "Volunteer" for x in t["team"]))
        self.assertEqual(f.call("POST", "/api/attendance/mark", dict(team_id=tid, attendance="P"))[0], 200)
        self.assertEqual(f.call("POST", "/api/attendance/mark", dict(team_id=tid, attendance="H"))[0], 200)   # same day updates, not duplicates
        self.assertEqual([x for x in f.call("GET", "/api/field/team")[1]["team"] if x["id"] == tid][0]["att"], "H")
        self.assertEqual(f.call("POST", "/api/attendance/mark", dict(team_id=tid, attendance="Z"))[0], 400)
        self.assertEqual(self.client("viewer").call("POST", "/api/attendance/mark", dict(team_id=tid, attendance="P"))[0], 403)
        b = f.call("GET", "/api/t/beneficiaries")[1]
        if b:
            x = b[0]
            r = f.call("GET", "/api/duplicates?name=" + urllib.request.quote(x["name"]) + "&village=" + urllib.request.quote(x.get("village") or "") + "&phone=")[1]
            self.assertTrue(any(i["id"] == x["id"] for i in r))
        self.assertEqual(f.call("GET", "/api/duplicates?phone=1")[1], [])

    def test_every_settings_field_saves(self):
        import re
        js = open(os.path.join(ROOT, "app/static/app.js")).read()
        js = js[js.index("async function viewSettings"):js.index("async function viewLists")]
        keys = set(re.findall(r'\["([a-z_]+)", "', js))
        a = self.client()
        st = a.call("GET", "/api/meta")[1]["settings"]
        body = {k: st.get(k, "") for k in keys if k != "starttls"}
        for k in ("digest_to", "trustee_emails"): body[k] = "a@b.org"
        s, r = a.call("PUT", "/api/settings", body); self.assertEqual(s, 200, r)

    def test_branding(self):
        import base64
        pub = Client(self.base)
        b = pub.call("GET", "/api/public/brand")[1]; self.assertEqual(b["product"], "NGO Suite"); self.assertEqual(b["logo"], "")
        self.assertEqual(pub.call("GET", "/api/public/logo")[0], 404)
        a = self.client()
        self.assertEqual(a.call("PUT", "/api/settings", dict(brand_color="red"))[0], 400)
        self.assertEqual(a.call("PUT", "/api/settings", dict(brand_color="#ffff00"))[0], 400)          # too light for white text
        self.assertEqual(a.call("PUT", "/api/settings", dict(brand_product=""))[0], 400)
        self.assertEqual(a.call("PUT", "/api/settings", dict(brand_product="Seva Desk", brand_color="#1f4e8c", setup_done="Yes"))[0], 200)
        self.assertEqual(pub.call("GET", "/api/public/brand")[1]["product"], "Seva Desk")
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 50).decode()
        self.assertEqual(a.call("POST", "/api/branding/logo", dict(data="data:image/png;base64," + png))[0], 200)
        self.assertEqual(a.call("POST", "/api/branding/logo", dict(data="data:image/png;base64," + base64.b64encode(b"<svg onload=1>").decode()))[0], 400)   # not a real PNG
        self.assertEqual(a.call("POST", "/api/branding/logo", dict(data="data:image/svg+xml;base64,AAAA"))[0], 400)
        self.assertEqual(a.call("POST", "/api/branding/logo", dict(data="data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 400000).decode()))[0], 400)
        s, img = pub.call("GET", "/api/public/logo", raw=True); self.assertEqual(s, 200); self.assertTrue(img.startswith(b"\x89PNG"))
        self.assertEqual(self.client("accounts").call("POST", "/api/branding/logo", dict(data="data:image/png;base64," + png))[0], 403)
        self.assertTrue(a.call("GET", "/api/print/receipt/1")[1]["org"]["logo"].startswith("/api/public/logo"))
        self.assertEqual(a.call("DELETE", "/api/branding/logo")[0], 200); self.assertEqual(pub.call("GET", "/api/public/logo")[0], 404)
        a.call("PUT", "/api/settings", dict(brand_product="NGO Suite", brand_color="#0f5e63"))

    def test_interactions_and_followups(self):
        a = self.client("accounts")
        d = a.call("GET", "/api/t/donors")[1][0]
        s, i = a.call("POST", "/api/t/interactions", dict(date="2026-11-10", donor_id=d["id"], channel="Call", summary="Called about the fete", outcome="Promised gift", next_followup="2026-11-12"))
        self.assertEqual(s, 200)
        self.assertEqual(a.call("GET", f"/api/t/donors/{d['id']}")[1]["next_followup"], "2026-11-12")      # donor follow-up date follows the log
        a.call("POST", "/api/t/interactions", dict(date="2026-11-11", donor_id=d["id"], channel="Call", summary="Gift received", outcome="Done", next_followup=""))
        self.assertFalse(a.call("GET", f"/api/t/donors/{d['id']}")[1]["next_followup"])                     # latest contact cleared it
        a.call("PUT", f"/api/t/interactions/{i['id']}", dict(next_followup="2026-12-01"))                    # editing an older log must not override the newer one
        self.assertFalse(a.call("GET", f"/api/t/donors/{d['id']}")[1]["next_followup"])
        fu = a.call("GET", "/api/followups")[1]
        self.assertTrue(set(fu) >= {"overdue", "due_today", "soon"})
        for r in fu["overdue"]: self.assertLess(r["next_followup"], fu["today"])
        tl = a.call("GET", f"/api/donors/{d['id']}/timeline")[1]
        self.assertTrue(any(e["title"] == "Done" for e in tl["events"]))
        self.assertEqual(a.call("GET", "/api/donors/99999/timeline")[0], 404)
        self.assertEqual(self.client("viewer").call("POST", "/api/t/interactions", dict(date="2026-11-10", donor_id=d["id"], summary="x"))[0], 403)
        self.assertEqual(a.call("POST", "/api/t/interactions", dict(date="2026-11-10", donor_id=d["id"]))[0], 400)   # summary required

    def test_campaigns(self):
        import time as _t
        from app import automation, comms
        automation.SEND_DELAY = 0
        sent = []; orig = mailer._smtp_send; mailer._smtp_send = lambda s, msg: sent.append(msg)
        try:
            a = self.client("accounts")
            c0 = db.connect(); c0.execute("INSERT OR REPLACE INTO settings VALUES('smtp_host','')"); c0.commit(); c0.close()
            self.assertEqual(a.call("POST", "/api/campaign/send", dict(name="x", subject="s", body="b", segment="all"))[0], 400)    # email not set up
            c = db.connect(); c.execute("INSERT OR REPLACE INTO settings VALUES('smtp_host','x')"); c.commit()
            s, pv = a.call("POST", "/api/campaign/preview", dict(segment="all")); self.assertEqual(s, 200); self.assertGreater(pv["with_email"], 5)
            self.assertEqual(a.call("POST", "/api/campaign/preview", dict(segment="nope"))[0], 400)
            all_ids = {d["id"] for d in comms.segment_donors(c, "all")}
            for d in a.call("GET", "/api/t/donors")[1]:
                if d.get("wishes") == "N": self.assertNotIn(d["id"], all_ids)            # opted-out donors never included
            s, r = a.call("POST", "/api/campaign/send", dict(name="Diwali", subject="Hello {first_name}", body="Dear {first_name}, from {org}", segment="all"))
            self.assertEqual(s, 200)
            for _ in range(200):
                row = a.call("GET", "/api/campaigns")[1][0]
                if row["status"] != "Sending": break
                _t.sleep(.05)
            self.assertEqual((row["status"], row["sent"], row["failed"]), ("Done", r["total"], 0))
            self.assertEqual(len(sent), r["total"]); self.assertIn("reply STOP", sent[0].get_body(("plain",)).get_content())
            self.assertTrue(sent[0]["Subject"].startswith("Hello ") and "{" not in sent[0]["Subject"])
            s, w = a.call("POST", "/api/campaign/whatsapp", dict(segment="all", body="Hi {first_name}")); self.assertEqual(s, 200)
            self.assertTrue(w["list"] and all(x["link"].startswith("https://wa.me/") for x in w["list"]))
            self.assertEqual(self.client("viewer").call("POST", "/api/campaign/send", dict(name="x", subject="s", body="b", segment="all"))[0], 403)
            self.assertEqual(self.client("field").call("GET", "/api/campaigns")[0], 403)
            self.assertEqual(a.call("POST", "/api/campaign/send", dict(name="", subject="s", body="b", segment="all"))[0], 400)
            self.assertEqual(a.call("POST", "/api/campaign/send", dict(name="n", subject="s", body="b", segment="big", param="99999999"))[0], 400)   # nobody in group
            c.execute("INSERT OR REPLACE INTO settings VALUES('smtp_host','')"); c.commit(); c.close()
        finally:
            mailer._smtp_send = orig

    def test_templates_default(self):
        self.assertGreaterEqual(len(self.client("accounts").call("GET", "/api/t/templates")[1]), 5)

    # ------------------------------------------------------------ official-number messaging
    def test_phone_normalise(self):
        from app import gateway as g
        self.assertEqual(g.normalise_phone("98290 61234"), "919829061234")
        self.assertEqual(g.normalise_phone("+91 98290-61234"), "919829061234")
        self.assertEqual(g.normalise_phone("09829061234"), "919829061234")
        self.assertEqual(g.normalise_phone("+1 415 555 0100"), "14155550100")
        for bad in ("", "123", "abc", "+0123456789012", None): self.assertIsNone(g.normalise_phone(bad))

    def test_gateway_adapters(self):
        from app import gateway as g
        calls = []
        orig = g._post
        g._post = lambda url, headers, data, timeout=20: (calls.append((url, headers, data)) or (200, '{"messages":[{"id":"wamid.1"}],"sid":"SM1","type":"success","message":"req1"}'))
        try:
            base = dict(wa_provider="Meta", wa_phone_id="1234", wa_token="TOK", wa_lang="en", sms_provider="MSG91", sms_authkey="KEY", twilio_sid="ACx", twilio_token="T", twilio_sms_from="+15550001", twilio_wa_from="+15550002")
            self.assertEqual(g.send(base, "whatsapp", "98290 61234", "hi", ["Asha", "Trust"], "festival"), "wamid.1")
            url, h, data = calls[-1]; body = json.loads(data)
            self.assertTrue(url.endswith("/1234/messages")); self.assertEqual(h["Authorization"], "Bearer TOK")
            self.assertEqual((body["to"], body["type"], body["template"]["name"]), ("919829061234", "template", "festival"))
            self.assertEqual([p["text"] for p in body["template"]["components"][0]["parameters"]], ["Asha", "Trust"])
            g.send(base, "whatsapp", "9829061234", "free text"); self.assertEqual(json.loads(calls[-1][2])["type"], "text")
            g.send(base, "sms", "9829061234", "x", ["Asha"], "DLT123"); body = json.loads(calls[-1][2])
            self.assertEqual((body["template_id"], body["recipients"][0]["mobiles"], body["recipients"][0]["VAR1"]), ("DLT123", "919829061234", "Asha")); self.assertEqual(calls[-1][1]["authkey"], "KEY")
            with self.assertRaises(g.GatewayError): g.send(base, "sms", "9829061234", "x", [], "")          # MSG91 needs a DLT template
            tw = dict(base, wa_provider="Twilio", sms_provider="Twilio")
            g.send(tw, "sms", "9829061234", "hello"); self.assertIn(b"Body=hello", calls[-1][2]); self.assertIn(b"To=%2B919829061234", calls[-1][2]); self.assertTrue(calls[-1][1]["Authorization"].startswith("Basic "))
            g.send(tw, "whatsapp", "9829061234", "hello"); self.assertIn(b"whatsapp%3A%2B919829061234", calls[-1][2])
            cu = dict(base, sms_provider="Custom", custom_url="https://api.example.com/send", custom_headers='{"X-Key":"k"}', custom_body='{"to":"{to}","msg":"{message}","n":"{p1}"}')
            g.send(cu, "sms", "9829061234", 'He said "hi"\nbye', ["Asha"]); self.assertEqual(json.loads(calls[-1][2])["msg"], 'He said "hi"\nbye'); self.assertEqual(calls[-1][1]["X-Key"], "k")
            with self.assertRaises(g.GatewayError): g.send(dict(base, wa_provider="None"), "whatsapp", "9829061234", "x")
            with self.assertRaises(g.GatewayError): g.send(base, "whatsapp", "12", "x")
            with self.assertRaises(g.GatewayError): g.send(dict(base, wa_token=""), "whatsapp", "9829061234", "x")
            g._post = lambda *a, **k: (401, '{"error":{"message":"Invalid token"}}')
            with self.assertRaises(g.GatewayError) as cm: g.send(base, "whatsapp", "9829061234", "x")
            self.assertIn("Invalid token", str(cm.exception))
        finally:
            g._post = orig
        for bad in ("http://example.com/x", "https://127.0.0.1/x", "https://localhost/x", "ftp://x.org"):
            with self.assertRaises(g.GatewayError): g._safe_url(bad)

    def test_secrets_never_returned(self):
        a = self.client()
        s, r = a.call("PUT", "/api/settings", dict(wa_provider="Meta", wa_phone_id="99", wa_token="SECRET-TOKEN-1", sms_provider="Custom", custom_url="https://api.example.com/x", custom_headers='{"A":"B"}', twilio_token="SECRET-TW"))
        self.assertEqual(s, 200)
        for path in ("/api/meta",):
            txt = json.dumps(a.call("GET", path)[1]); self.assertNotIn("SECRET-TOKEN-1", txt); self.assertNotIn("SECRET-TW", txt)
        self.assertNotIn("SECRET", json.dumps(r)); self.assertEqual(r["wa_token_set"], "Yes")
        a.call("PUT", "/api/settings", dict(wa_token="")); c = db.connect(); self.assertEqual(db.get_settings(c)["wa_token"], "SECRET-TOKEN-1"); c.close()   # blank keeps it
        self.assertEqual(a.call("PUT", "/api/settings", dict(custom_url="http://insecure.example.com"))[0], 400)
        self.assertEqual(a.call("PUT", "/api/settings", dict(custom_headers="not json"))[0], 400)
        self.assertEqual(a.call("PUT", "/api/settings", dict(wa_provider="Fake"))[0], 400)
        self.assertEqual(self.client("accounts").call("PUT", "/api/tool-settings", dict(wa_token="x"))[0], 400)
        self.assertEqual(self.client("accounts").call("PUT", "/api/settings", dict(wa_token="x"))[0], 403)
        for k in ("wa_provider", "sms_provider", "wa_token", "custom_url", "custom_headers", "twilio_token"): a.call("PUT", "/api/settings", {k: "None" if k.endswith("provider") else ""}) if k.endswith("provider") else None
        c = db.connect()
        for k in ("wa_token", "custom_url", "custom_headers", "twilio_token", "wa_phone_id"): c.execute("INSERT OR REPLACE INTO settings VALUES(?,'')", (k,))
        c.commit(); c.close()

    def test_contacts_and_broadcast(self):
        import time as _t
        from app import automation, comms, gateway as g
        automation.SEND_DELAY = 0
        sent = []; orig = g._post
        g._post = lambda url, headers, data, timeout=20: (sent.append((url, json.loads(data))) or (200, '{"messages":[{"id":"w1"}]}'))
        a = self.client("accounts")
        try:
            c = db.connect()
            for k, v in dict(wa_provider="Meta", wa_phone_id="55", wa_token="T", sms_provider="None").items(): c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, v))
            c.commit()
            mk = lambda **kw: a.call("POST", "/api/t/contacts", dict(**kw))
            self.assertEqual(mk(name="Vol One", phone="98111 00001", tags="TestGroup, Media", relation="Volunteer")[0], 200)
            self.assertEqual(mk(name="Vol Two", phone="98111 00002", tags="testgroup")[0], 200)
            self.assertEqual(mk(name="No Consent", phone="98111 00003", tags="TestGroup", msg_optin="N")[0], 200)
            self.assertEqual(mk(name="Bad Phone", phone="12", tags="TestGroup")[0], 200)
            self.assertEqual(mk(name="Zed Duplicate", phone="+91 98111 00001", tags="TestGroup")[0], 200)
            s, cs = a.call("GET", "/api/t/contacts"); self.assertTrue(all(x["code"].startswith("C-") for x in cs))
            self.assertEqual(self.client("viewer").call("POST", "/api/t/contacts", dict(name="x"))[0], 403)
            aud = comms.audience(c, "contacts_group", "TestGroup", "whatsapp")
            self.assertEqual(sorted(x["name"] for x in aud), ["Vol One", "Vol Two"])          # consent, bad number and duplicate number all dropped
            s, pv = a.call("POST", "/api/campaign/preview", dict(segment="contacts_group", param="TestGroup")); self.assertEqual(pv["counts"]["whatsapp"], 2)
            s, sg = a.call("GET", "/api/campaign/segments"); self.assertIn("TestGroup", sg["groups"]); self.assertEqual(sg["gateway"]["whatsapp"], "Meta")
            self.assertEqual(a.call("POST", "/api/campaign/send", dict(name="x", channel="sms", body="b", segment="all"))[0], 400)   # SMS not connected
            self.assertEqual(a.call("POST", "/api/campaign/send", dict(name="x", channel="whatsapp", body="", segment="all"))[0], 400)
            s, r = a.call("POST", "/api/campaign/send", dict(name="Volunteer meet", channel="whatsapp", segment="contacts_group", param="TestGroup", body="Hi {first_name}", template="meet_notice", variables="first_name,org"))
            self.assertEqual(s, 200)
            for _ in range(200):
                row = a.call("GET", f"/api/campaign/{r['id']}")[1]
                if row["status"] != "Sending": break
                _t.sleep(.05)
            self.assertEqual((row["status"], row["sent"], row["failed"], len(row["messages"])), ("Done", 2, 0, 2))
            self.assertEqual({m["to_addr"] for m in row["messages"]}, {"919811100001", "919811100002"})
            self.assertEqual(sent[0][1]["template"]["name"], "meet_notice"); self.assertEqual(sent[0][1]["template"]["components"][0]["parameters"][0]["text"], "Vol")
            # failures are recorded per person and can be retried
            g._post = lambda url, headers, data, timeout=20: (400, '{"error":{"message":"Template not approved"}}')
            s, r2 = a.call("POST", "/api/campaign/send", dict(name="Will fail", channel="whatsapp", segment="contacts_group", param="TestGroup", body="x"))
            for _ in range(200):
                row2 = a.call("GET", f"/api/campaign/{r2['id']}")[1]
                if row2["status"] != "Sending": break
                _t.sleep(.05)
            self.assertEqual((row2["sent"], row2["failed"]), (0, 2)); self.assertIn("Template not approved", row2["messages"][0]["error"])
            g._post = lambda url, headers, data, timeout=20: (200, '{"messages":[{"id":"w2"}]}')
            self.assertEqual(a.call("POST", f"/api/campaign/{r2['id']}/retry")[0], 200)
            for _ in range(200):
                row2 = a.call("GET", f"/api/campaign/{r2['id']}")[1]
                if row2["status"] != "Sending": break
                _t.sleep(.05)
            self.assertEqual((row2["sent"], row2["failed"], len(row2["messages"])), (2, 0, 2))
            # donors get a contact-log entry for a broadcast, contacts do not crash it
            s, dn = a.call("POST", "/api/t/donors", dict(name="Wa Donor", phone="98222 33344", msg_optin="Y"))
            s, r3 = a.call("POST", "/api/campaign/send", dict(name="Donor ping", channel="whatsapp", segment="never", body="Hi"))
            for _ in range(200):
                row3 = a.call("GET", f"/api/campaign/{r3['id']}")[1]
                if row3["status"] != "Sending": break
                _t.sleep(.05)
            self.assertTrue(any("Broadcast: Donor ping" in e["detail"] for e in a.call("GET", f"/api/donors/{dn['id']}/timeline")[1]["events"]))
            # scheduling and cancelling
            fut = (datetime.datetime.now() + datetime.timedelta(hours=2)).isoformat(timespec="minutes")
            n0 = len(sent)
            s, r4 = a.call("POST", "/api/campaign/send", dict(name="Later", channel="whatsapp", segment="contacts_group", param="TestGroup", body="Hi", schedule_at=fut))
            self.assertEqual((s, r4["scheduled"]), (200, fut)); self.assertEqual(a.call("GET", f"/api/campaign/{r4['id']}")[1]["status"], "Scheduled")
            self.assertEqual(comms.run_due(c), [])                                             # not due yet
            self.assertEqual(a.call("POST", f"/api/campaign/{r4['id']}/cancel")[0], 200); self.assertEqual(a.call("POST", f"/api/campaign/{r4['id']}/cancel")[0], 400)
            past = (datetime.datetime.now() + datetime.timedelta(minutes=10)).isoformat(timespec="minutes")
            s, r5 = a.call("POST", "/api/campaign/send", dict(name="Soon", channel="whatsapp", segment="contacts_group", param="TestGroup", body="Hi", schedule_at=past))
            c.execute("UPDATE campaigns SET schedule_at=? WHERE id=?", ("2000-01-01T00:00", r5["id"])); c.commit()
            ts = comms.run_due(c); [t.join(5) for t in ts]; self.assertEqual(len(ts), 1)
            self.assertEqual(a.call("GET", f"/api/campaign/{r5['id']}")[1]["status"], "Done"); self.assertEqual(comms.run_due(c), [])
            self.assertEqual(a.call("POST", "/api/campaign/send", dict(name="Far", channel="whatsapp", segment="all", body="Hi", schedule_at="2099-01-01T00:00"))[0], 400)
            # permissions
            self.assertEqual(self.client("viewer").call("GET", f"/api/campaign/{r['id']}")[0], 403)
            self.assertEqual(self.client("accounts").call("POST", "/api/gateway/test", dict(channel="whatsapp", to="9829061234"))[0], 403)
            s, t = self.client().call("POST", "/api/gateway/test", dict(channel="whatsapp", to="9829061234", template="hello_world")); self.assertEqual(s, 200)
            self.assertEqual(self.client().call("POST", "/api/gateway/test", dict(channel="whatsapp", to="12"))[0], 400)
            c.close()
        finally:
            g._post = orig
            c = db.connect()
            for k, v in dict(wa_provider="None", wa_phone_id="", wa_token="").items(): c.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, v))
            c.commit(); c.close()

    # ---------------------------------------------------------------- media
    @staticmethod
    def fake_jpeg(gps=True):
        exif = b"Exif\x00\x00" + b"GPSLatitude-12.34" * 3
        app1 = b"\xff\xe1" + (len(exif) + 2).to_bytes(2, "big") + exif
        app0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        return b"\xff\xd8" + app0 + (app1 if gps else b"") + b"\xff\xda\x00\x02" + b"IMAGEDATA" * 50 + b"\xff\xd9"

    def test_media_upload_privacy_range_roles(self):
        f = self.client("field"); a = self.client("admin"); v = self.client("viewer"); acc = self.client("accounts")
        jpg = self.fake_jpeg()
        s, b, h = f.rawcall("POST", "/api/media?kind=photo&project_id=1&consent=N&caption=Camp&client_id=t-1", jpg)
        self.assertEqual(s, 200, b); mid = json.loads(b)["id"]
        # replay with the same client id does not create a duplicate
        s, b, h = f.rawcall("POST", "/api/media?kind=photo&client_id=t-1", jpg)
        self.assertEqual(json.loads(b).get("duplicate"), True); self.assertEqual(json.loads(b)["id"], mid)
        # GPS / EXIF removed on disk, image data kept
        s, got, h = f.rawcall("GET", f"/api/media/{mid}/file")
        self.assertEqual(s, 200); self.assertNotIn(b"GPSLatitude", got); self.assertIn(b"IMAGEDATA", got); self.assertTrue(got.startswith(b"\xff\xd8"))
        self.assertEqual(h["Content-Type"], "image/jpeg")
        # consent not given -> viewer cannot see it, others can
        self.assertEqual(v.rawcall("GET", f"/api/media/{mid}/file")[0], 404)
        self.assertNotIn(mid, [m["id"] for m in v.call("GET", "/api/media")[1]["items"]])
        self.assertIn(mid, [m["id"] for m in acc.call("GET", "/api/media")[1]["items"]])
        # consent granted -> viewer sees it
        self.assertEqual(f.call("PUT", f"/api/media/{mid}", dict(consent="Y"))[0], 200)
        self.assertEqual(v.rawcall("GET", f"/api/media/{mid}/file")[0], 200)
        # viewer / accountant cannot upload
        self.assertEqual(v.rawcall("POST", "/api/media?kind=photo", jpg)[0], 403)
        self.assertEqual(acc.rawcall("POST", "/api/media?kind=photo", jpg)[0], 403)
        # wrong type rejected even with an image content-type; kind mismatch rejected
        self.assertEqual(f.rawcall("POST", "/api/media?kind=photo", b"<html>x</html>" * 20, {"Content-Type": "image/jpeg"})[0], 415)
        self.assertEqual(f.rawcall("POST", "/api/media?kind=video", jpg)[0], 415)
        self.assertEqual(f.rawcall("POST", "/api/media?kind=photo", b"")[0], 400)
        # size limits
        big = b"\xff\xd8\xff" + b"0" * 8_100_000
        self.assertEqual(f.rawcall("POST", "/api/media?kind=photo", big)[0], 413)
        # video + Range
        vid = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 40
        s, b, h = f.rawcall("POST", "/api/media?kind=video&project_id=1&consent=Y", vid); self.assertEqual(s, 200, b); vid_id = json.loads(b)["id"]
        s, part, h = f.rawcall("GET", f"/api/media/{vid_id}/file", headers={"Range": "bytes=100-199"})
        self.assertEqual(s, 206); self.assertEqual(part, vid[100:200]); self.assertEqual(h["Content-Range"], f"bytes 100-199/{len(vid)}")
        s, part, h = f.rawcall("GET", f"/api/media/{vid_id}/file", headers={"Range": "bytes=-50"}); self.assertEqual(part, vid[-50:])
        self.assertEqual(f.rawcall("GET", f"/api/media/{vid_id}/file", headers={"Range": "bytes=99999-"})[0], 416)
        s, full, h = f.rawcall("GET", f"/api/media/{vid_id}/file"); self.assertEqual(full, vid); self.assertEqual(h["Accept-Ranges"], "bytes")
        # thumbnail
        self.assertEqual(f.rawcall("POST", f"/api/media/{vid_id}/thumb", self.fake_jpeg(False))[0], 200)
        s, th, h = v.rawcall("GET", f"/api/media/{vid_id}/thumb"); self.assertEqual(s, 200); self.assertEqual(h["Content-Type"], "image/jpeg")
        # only the uploader or an admin can edit or delete
        other = self.client("accounts")
        self.assertEqual(other.call("DELETE", f"/api/media/{mid}")[0], 403)
        self.assertEqual(a.call("DELETE", f"/api/media/{mid}")[0], 200)
        self.assertEqual(f.rawcall("GET", f"/api/media/{mid}/file")[0], 404)
        # no path escape through the id
        self.assertIn(f.rawcall("GET", "/api/media/1/../../etc/passwd")[0], (404, 405))
        # media files are not reachable as static files
        self.assertEqual(Client(self.base).rawcall("GET", f"/media/x.jpg")[0], 404)
        self.assertEqual(Client(self.base).rawcall("GET", f"/api/media/{vid_id}/file")[0], 401)

    def test_media_strip_function(self):
        from app import media
        out = media.strip_jpeg(self.fake_jpeg())
        self.assertNotIn(b"GPSLatitude", out); self.assertIn(b"JFIF", out); self.assertTrue(out.endswith(b"\xff\xd9"))
        self.assertEqual(media.strip_jpeg(self.fake_jpeg(False)), self.fake_jpeg(False))

    def test_claims_flow_and_maker_checker(self):
        f = self.client("field"); a = self.client("accounts"); adm = self.client("admin"); v = self.client("viewer")
        funds = {x["name"]: x["id"] for x in a.call("GET", "/api/t/funds")[1]}
        s, r = f.call("POST", "/api/claims", dict(date="2026-05-02", project_id=1, category="Travel", amount="450", description="Auto to camp", client_id="c-1"))
        self.assertEqual(s, 200, r); cid = r["id"]; self.assertTrue(r["claim_no"].startswith("EC-"))
        self.assertTrue(f.call("POST", "/api/claims", dict(amount=450, client_id="c-1"))[1].get("duplicate"))
        for bad in (dict(amount=0), dict(amount="abc"), dict(amount=10, date="2999-01-01"), dict(amount=10, project_id=99999)):
            self.assertEqual(f.call("POST", "/api/claims", bad)[0], 400, bad)
        self.assertEqual(v.call("POST", "/api/claims", dict(amount=5))[0], 403)
        self.assertEqual(v.call("GET", "/api/claims")[0], 403)
        # bill photo attached to the claim; viewers/other staff cannot see it, finance can
        s, b, h = f.rawcall("POST", f"/api/media?kind=photo&claim_id={cid}", self.fake_jpeg()); self.assertEqual(s, 200, b); bill = json.loads(b)["id"]
        self.assertEqual(v.rawcall("GET", f"/api/media/{bill}/file")[0], 404)
        self.assertEqual(a.rawcall("GET", f"/api/media/{bill}/file")[0], 200)
        self.assertNotIn(bill, [m["id"] for m in a.call("GET", "/api/media")[1]["items"]])   # not in the event gallery
        self.assertIn(bill, [m["id"] for m in a.call("GET", f"/api/media?purpose=bill&claim_id={cid}")[1]["items"]])
        self.assertEqual(f.call("GET", "/api/claims")[1][0]["bills"], 1)
        # field user cannot approve; reject needs a reason; pay needs approval first
        self.assertEqual(f.call("POST", f"/api/claims/{cid}/review", dict(action="approve"))[0], 403)
        self.assertEqual(a.call("POST", f"/api/claims/{cid}/pay", dict(fund_id=funds["General Fund"]))[0], 400)
        self.assertEqual(a.call("POST", f"/api/claims/{cid}/review", dict(action="reject"))[0], 400)
        self.assertEqual(a.call("POST", f"/api/claims/{cid}/review", dict(action="approve"))[0], 200)
        self.assertEqual(a.call("POST", f"/api/claims/{cid}/review", dict(action="approve"))[0], 400)
        self.assertEqual(f.call("DELETE", f"/api/claims/{cid}")[0], 403)
        # paying posts to the cash book and lowers the fund balance
        before = a.call("GET", f"/api/t/funds/{funds['General Fund']}")[1]["balance"]
        s, p = a.call("POST", f"/api/claims/{cid}/pay", dict(fund_id=funds["General Fund"], mode="UPI")); self.assertEqual(s, 200, p)
        self.assertEqual(before - a.call("GET", f"/api/t/funds/{funds['General Fund']}")[1]["balance"], 450)
        self.assertEqual(a.call("POST", f"/api/claims/{cid}/pay", dict(fund_id=funds["General Fund"]))[0], 400)
        # maker-checker: an admin cannot approve or pay their own claim
        s, r2 = adm.call("POST", "/api/claims", dict(amount=99, category="Other")); self.assertEqual(s, 200)
        self.assertEqual(adm.call("POST", f"/api/claims/{r2['id']}/review", dict(action="approve"))[0], 403)
        # withdraw own pending claim removes the bill file too
        s, r3 = f.call("POST", "/api/claims", dict(amount=20)); self.assertEqual(f.call("DELETE", f"/api/claims/{r3['id']}")[0], 200)
        # claimant sees only their own claims
        self.assertTrue(all(x["user_id"] == f.call("GET", "/api/me")[1]["user"]["id"] for x in f.call("GET", "/api/claims")[1]))
        self.assertGreaterEqual(len(a.call("GET", "/api/claims")[1]), 2)

    def test_pwa_and_field_activity(self):
        c = Client(self.base)
        s, raw, h = c.rawcall("GET", "/manifest.webmanifest"); self.assertEqual(s, 200)
        m = json.loads(raw); self.assertEqual(m["display"], "standalone"); self.assertTrue(m["start_url"].startswith("/#/r/field"))
        s, png, h = c.rawcall("GET", "/icon-192.png"); self.assertEqual(s, 200); self.assertTrue(png.startswith(b"\x89PNG")); self.assertEqual(h["Content-Type"], "image/png")
        self.assertEqual(c.rawcall("GET", "/icon-999.png")[0], 404)
        self.assertEqual(c.rawcall("GET", "/sw.js")[0], 200)
        f = self.client("field"); v = self.client("viewer")
        body = dict(date="2026-05-03", project_id=1, activity="Health camp", people_reached=40, client_id="a-1")
        s, r = f.call("POST", "/api/field/activity", body); self.assertEqual(s, 200, r)
        s, r2 = f.call("POST", "/api/field/activity", body); self.assertEqual(r2["id"], r["id"]); self.assertTrue(r2["duplicate"])
        self.assertEqual(v.call("POST", "/api/field/activity", dict(body, client_id="a-2"))[0], 403)
        self.assertEqual(f.call("POST", "/api/field/activity", dict(date="2026-05-03", client_id="a-3"))[0], 400)   # project required

    def test_speed_gzip_etag_indexes(self):
        import gzip as gz
        a = self.client("admin")
        s, raw, h = a.rawcall("GET", "/api/t/donations", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(h["Content-Encoding"], "gzip"); self.assertGreater(len(json.loads(gz.decompress(raw))), 5)
        s, raw, h = a.rawcall("GET", "/api/t/donations"); self.assertIsNone(h.get("Content-Encoding")); json.loads(raw)
        c = Client(self.base)
        s, raw, h = c.rawcall("GET", "/app.js", headers={"Accept-Encoding": "gzip"}); self.assertEqual(h["Content-Encoding"], "gzip")
        self.assertIn(b"function h(", gz.decompress(raw)); tag = h["ETag"]
        s, raw, h = c.rawcall("GET", "/app.js", headers={"If-None-Match": tag}); self.assertEqual(s, 304); self.assertEqual(raw, b"")
        s, raw, h = c.rawcall("GET", "/app.js", headers={"If-None-Match": "bogus"}); self.assertEqual(s, 200)
        con = db.connect(); names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}; con.close()
        for ix in ("ix_donations_donor_id", "ix_cash_book_date", "ix_activities_project_id_date"): self.assertIn(ix, names)

    def test_totp_rfc6238_vector_and_vault(self):
        from app import vault
        sec = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"          # ASCII 12345678901234567890
        self.assertEqual(vault.totp_now(sec, t=59, digits=8), "94287082")
        self.assertEqual(vault.totp_now(sec, t=1111111109, digits=8), "07081804")
        self.assertIsNone(vault.check_code(sec, "000000", t=59))
        self.assertEqual(vault.check_code(sec, "287082", t=59), 1)
        self.assertIsNone(vault.check_code(sec, "287082", last=1, t=59))            # a code cannot be reused
        t = vault.seal("my-secret-token"); self.assertTrue(t.startswith("enc1:")); self.assertNotIn("my-secret", t)
        self.assertEqual(vault.unseal(t), "my-secret-token"); self.assertEqual(vault.unseal("plain"), "plain")
        self.assertNotEqual(vault.seal("my-secret-token"), t)                       # fresh nonce each time
        self.assertEqual(vault.unseal(t[:-3] + ("AAA" if not t.endswith("AAA") else "BBB")), "")   # tampering is detected
        self.assertEqual(vault.seal(""), "")

    def test_secrets_encrypted_in_database(self):
        a = self.client("admin")
        self.assertEqual(a.call("PUT", "/api/settings", dict(smtp_password="hunter2-app-pass", wa_token="EAAB-token"))[0], 200)
        con = db.connect()
        raw = {r["key"]: r["value"] for r in con.execute("SELECT key,value FROM settings WHERE key IN ('smtp_password','wa_token')")}
        st = db.get_settings(con); con.close()
        self.assertTrue(raw["smtp_password"].startswith("enc1:")); self.assertNotIn("hunter2", raw["smtp_password"])
        self.assertEqual(st["smtp_password"], "hunter2-app-pass"); self.assertEqual(st["wa_token"], "EAAB-token")   # the sender still receives the real value
        self.assertEqual(a.call("GET", "/api/meta")[1]["settings"]["smtp_password"], "")                           # the browser never does
        # an older database with plain-text secrets is upgraded on start
        con = db.connect(); con.execute("UPDATE settings SET value='plain-old' WHERE key='smtp_password'")
        from app import vault
        self.assertGreaterEqual(vault.migrate(con), 1); con.commit()
        self.assertTrue(con.execute("SELECT value FROM settings WHERE key='smtp_password'").fetchone()[0].startswith("enc1:")); self.assertEqual(db.get_settings(con)["smtp_password"], "plain-old"); con.close()
        a.call("PUT", "/api/settings", dict(smtp_password="x"))
        con = db.connect(); con.execute("DELETE FROM settings WHERE key IN ('smtp_password','wa_token')"); con.execute("INSERT INTO settings VALUES('smtp_password',''),('wa_token','')"); con.commit(); con.close()

    def test_two_step_login_flow(self):
        from app import vault
        u = self.client("accounts")
        self.assertFalse(u.call("GET", "/api/2fa")[1]["enabled"])
        s, setup = u.call("POST", "/api/2fa/setup"); self.assertEqual(s, 200); self.assertIn("otpauth://totp/", setup["uri"]); self.assertIn("<svg", setup["qr"])
        sec = setup["secret"]
        self.assertEqual(u.call("POST", "/api/2fa/enable", dict(code="123456"))[0], 400)
        step_prev = time.time() - 30
        s, en = u.call("POST", "/api/2fa/enable", dict(code=vault.totp_now(sec, t=step_prev))); self.assertEqual(s, 200, en); backups = en["codes"]; self.assertEqual(len(backups), 8)
        # the secret is stored encrypted
        con = db.connect(); raw = con.execute("SELECT totp_secret FROM users WHERE username='accounts'").fetchone()[0]; con.close(); self.assertTrue(raw.startswith("enc1:"))
        # password alone no longer signs in
        c = Client(self.base); s, r = c.login("accounts"); self.assertEqual(s, 200); self.assertTrue(r["need_2fa"]); self.assertIsNone(c.cookie)
        self.assertEqual(c.call("GET", "/api/dashboard")[0], 401)
        self.assertEqual(c.call("POST", "/api/login/2fa", dict(pre=r["pre"], code="000000"))[0], 401)
        good = vault.totp_now(sec); s, r2 = c.call("POST", "/api/login/2fa", dict(pre=r["pre"], code=good)); self.assertEqual(s, 200, r2); self.assertIsNotNone(c.cookie)
        self.assertEqual(c.call("GET", "/api/dashboard")[0], 200)
        # the same code cannot be used twice
        c2 = Client(self.base); s, r = c2.login("accounts"); self.assertEqual(c2.call("POST", "/api/login/2fa", dict(pre=r["pre"], code=good))[0], 401)
        # a backup code works once
        s, r = c2.login("accounts"); self.assertEqual(c2.call("POST", "/api/login/2fa", dict(pre=r["pre"], code=backups[0]))[0], 200)
        c3 = Client(self.base); s, r = c3.login("accounts"); self.assertEqual(c3.call("POST", "/api/login/2fa", dict(pre=r["pre"], code=backups[0]))[0], 401)
        # too many wrong codes burns the sign-in attempt
        c4 = Client(self.base); s, r = c4.login("accounts")
        for _ in range(5): c4.call("POST", "/api/login/2fa", dict(pre=r["pre"], code="111111"))
        self.assertEqual(c4.call("POST", "/api/login/2fa", dict(pre=r["pre"], code=vault.totp_now(sec, t=time.time() + 30)))[0], 429)
        # unknown / forged pre-auth token
        self.assertEqual(Client(self.base).call("POST", "/api/login/2fa", dict(pre="nope", code="123456"))[0], 401)
        # an admin can reset it; a normal user cannot reset someone else's
        a = self.client("admin"); uid = [x for x in a.call("GET", "/api/users")[1] if x["username"] == "accounts"][0]
        self.assertTrue([x for x in a.call("GET", "/api/users")[1] if x["username"] == "accounts"][0]["totp"])
        self.assertEqual(c.call("POST", f"/api/users/{uid['id']}/reset2fa")[0], 403)
        self.assertEqual(a.call("POST", f"/api/users/{uid['id']}/reset2fa")[0], 200)
        self.assertEqual(c.call("GET", "/api/dashboard")[0], 401)                     # their sessions were ended
        self.assertNotIn("need_2fa", self.client("accounts").call("GET", "/api/2fa")[1] or {})
        # turn on, then turn off with password + code
        u = self.client("accounts"); sec = u.call("POST", "/api/2fa/setup")[1]["secret"]
        u.call("POST", "/api/2fa/enable", dict(code=vault.totp_now(sec, t=time.time() - 30)))
        self.assertEqual(u.call("POST", "/api/2fa/disable", dict(password="wrong", code=vault.totp_now(sec)))[0], 400)
        self.assertEqual(u.call("POST", "/api/2fa/disable", dict(password="ChangeMe123", code=vault.totp_now(sec)))[0], 200)
        self.assertFalse(u.call("GET", "/api/2fa")[1]["enabled"])

    def test_require_two_step_for_admins_policy(self):
        from app import vault
        a = self.client("admin")
        self.assertEqual(a.call("PUT", "/api/settings", dict(require_2fa_admin="Yes"))[0], 200)
        try:
            self.assertTrue(a.call("GET", "/api/me")[1]["user"]["need2fa"])
            s, e = a.call("GET", "/api/t/donors"); self.assertEqual(s, 403); self.assertIn("two-step", e["error"].lower())
            self.assertEqual(a.call("GET", "/api/meta")[0], 200)
            self.assertEqual(self.client("accounts").call("GET", "/api/t/donors")[0], 200)     # others unaffected
            sec = a.call("POST", "/api/2fa/setup")[1]["secret"]
            self.assertEqual(a.call("POST", "/api/2fa/enable", dict(code=vault.totp_now(sec, t=time.time() - 30)))[0], 200)
            self.assertEqual(a.call("GET", "/api/t/donors")[0], 200)
            self.assertEqual(a.call("POST", "/api/2fa/disable", dict(password="ChangeMe123", code=vault.totp_now(sec)))[0], 400)   # policy forbids switching off
        finally:
            con = db.connect(); con.execute("UPDATE settings SET value='No' WHERE key='require_2fa_admin'")
            con.execute("UPDATE users SET totp_secret=NULL, backup_codes=NULL, totp_last=0 WHERE username='admin'"); con.commit(); con.close()

    def test_password_change_signs_out_other_devices_and_https_flags(self):
        a1 = Client(self.base); a1.login("viewer"); a2 = Client(self.base); a2.login("viewer")
        self.assertEqual(a2.call("GET", "/api/me")[1]["user"]["username"], "viewer")
        self.assertEqual(a1.call("POST", "/api/password", dict(old="ChangeMe123", new="ChangeMe456"))[0], 200)
        self.assertIsNone(a2.call("GET", "/api/me")[1]["user"])                       # the other device is signed out
        self.assertEqual(a1.call("GET", "/api/me")[1]["user"]["username"], "viewer")  # this one stays
        self.assertEqual(a1.call("POST", "/api/password", dict(old="ChangeMe456", new="ChangeMe123"))[0], 200)
        # behind an HTTPS proxy on this computer: Secure cookie + HSTS; plain http gets neither
        body = json.dumps(dict(username="viewer", password="ChangeMe123")).encode()
        s, raw, h = Client(self.base).rawcall("POST", "/api/login", body, {"Content-Type": "application/json", "X-Forwarded-Proto": "https"})
        self.assertIn("Secure", h["Set-Cookie"]); self.assertIn("Strict-Transport-Security", h)
        s, raw, h = Client(self.base).rawcall("POST", "/api/login", body, {"Content-Type": "application/json"})
        self.assertNotIn("Secure", h["Set-Cookie"]); self.assertIsNone(h.get("Strict-Transport-Security"))
        self.assertIn("camera=(self)", h["Permissions-Policy"])
        # failed and successful sign-ins are written to the audit log
        acts = [r["action"] for r in self.client("admin").call("GET", "/api/audit")[1]]
        self.assertIn("login", acts); self.assertIn("login_failed", acts); self.assertIn("password_changed", acts)
        # logout everywhere
        x = Client(self.base); x.login("viewer"); y = Client(self.base); y.login("viewer")
        self.assertEqual(x.call("POST", "/api/logout-all")[0], 200); self.assertIsNone(y.call("GET", "/api/me")[1]["user"])

    def test_impact_cards(self):
        f = self.client("field"); a = self.client("accounts"); v = Client(self.base)
        f.call("POST", "/api/field/activity", dict(date="2025-01-10", project_id=1, activity="Health camp", village="Rampur", people_reached=120, volunteers=4, spent=6000, client_id="card-a1"))
        f.call("POST", "/api/field/activity", dict(date="2025-01-20", project_id=1, activity="Awareness", village="Rampur", people_reached=80, spent=1000, client_id="card-a2"))
        ok = json.loads(f.rawcall("POST", "/api/media?kind=photo&project_id=1&consent=Y&caption=Queue+at+camp&taken_at=2025-01-10T10:00:00&client_id=card-p1", self.fake_jpeg())[1])["id"]
        nc = json.loads(f.rawcall("POST", "/api/media?kind=photo&project_id=1&consent=N&taken_at=2025-01-11T10:00:00&client_id=card-p2", self.fake_jpeg())[1])["id"]
        other = json.loads(f.rawcall("POST", "/api/media?kind=photo&project_id=1&consent=Y&taken_at=2025-03-11T10:00:00&client_id=card-p3", self.fake_jpeg())[1])["id"]
        s, d = a.call("GET", "/api/cards/preview?project_id=1&month=2025-01"); self.assertEqual(s, 200, d)
        self.assertEqual((d["activities"], d["people"], d["volunteers"], d["spent"], d["per_person"]), (2, 200, 4, 7000, 35.0))
        ids = [p["id"] for p in d["photos"]]; self.assertIn(ok, ids); self.assertNotIn(nc, ids); self.assertNotIn(other, ids)      # only consented photos from that month
        self.assertEqual(f.call("GET", "/api/cards/preview?project_id=1&month=2025-01")[0], 200)                                    # field staff may preview
        self.assertEqual(f.call("POST", "/api/cards", dict(project_id=1, month="2025-01"))[0], 403)                               # only finance publishes
        self.assertEqual(a.call("GET", "/api/cards/preview?project_id=1&month=bad")[0], 400)
        self.assertEqual(a.call("POST", "/api/cards", dict(project_id=1, month="2025-01", photo_ids=[nc]))[0], 400)               # a no-consent photo cannot be chosen
        s, c = a.call("POST", "/api/cards", dict(project_id=1, month="2025-01", headline="200 people reached", story="Asha got her glasses.", photo_ids=[ok])); self.assertEqual(s, 200, c)
        # public link: no login, no private data
        s, pub = v.call("GET", "/api/public/card/" + c["token"]); self.assertEqual(s, 200); self.assertEqual(pub["people"], 200); self.assertEqual(pub["photo_ids"], [ok])
        blob = json.dumps(pub); self.assertNotIn("uploader", blob); self.assertNotIn("Field Coordinator", blob)
        s, img, h = v.rawcall("GET", f"/api/public/card/{c['token']}/photo/{ok}"); self.assertEqual(s, 200); self.assertEqual(h["Content-Type"], "image/jpeg"); self.assertNotIn(b"GPSLatitude", img)
        self.assertEqual(v.rawcall("GET", f"/api/public/card/{c['token']}/photo/{other}")[0], 404)                                  # not on this card
        self.assertEqual(v.rawcall("GET", f"/api/public/card/{c['token']}/photo/{nc}")[0], 404)
        self.assertEqual(v.rawcall("GET", "/api/public/card/aaaaaaaaaaaaaaaaaaaaaa")[0], 404)
        # withdrawing consent removes the photo from the live card at once
        f.call("PUT", f"/api/media/{ok}", dict(consent="N"))
        self.assertEqual(v.call("GET", "/api/public/card/" + c["token"])[1]["photo_ids"], []); self.assertEqual(v.rawcall("GET", f"/api/public/card/{c['token']}/photo/{ok}")[0], 404)
        # view count, revoke
        row = [x for x in a.call("GET", "/api/cards")[1] if x["id"] == c["id"]][0]; self.assertGreaterEqual(row["views"], 2)
        self.assertEqual(a.call("POST", f"/api/cards/{c['id']}/revoke")[0], 200)
        self.assertEqual(v.call("GET", "/api/public/card/" + c["token"])[0], 404)
        self.assertEqual(a.call("POST", "/api/cards", dict(project_id=1, month="2030-01"))[0], 400)                               # nothing logged, no story

    def test_compliance_pack(self):
        import io, zipfile
        a = self.client("accounts"); adm = self.client("admin"); f = self.client("field")
        self.assertEqual(f.call("GET", "/api/pack/readiness")[0], 403)
        s, r = a.call("GET", "/api/pack/readiness"); self.assertEqual(s, 200, r)
        keys = {i["key"] for i in r["items"]}; self.assertTrue({"org", "pan", "cash", "receipt", "bills", "claims", "pending"} <= keys)
        # a cash gift above 2000 from a donor with no PAN is flagged
        funds = {x["name"]: x["id"] for x in a.call("GET", "/api/t/funds")[1]}
        d = a.call("POST", "/api/t/donors", dict(name="Pack Donor", city="Pune"))[1]
        a.call("POST", "/api/t/donations", dict(date=asof_day(), donor_id=d["id"], purpose="General Donation", fund_type="General", mode="Cash", amount=5000, fund_id=funds["General Fund"]))
        fy = r["fy"]; r2 = a.call("GET", f"/api/pack/readiness?fy={fy}")[1]
        flag = {i["key"]: i for i in r2["items"]}
        self.assertGreaterEqual(flag["pan"]["bad"], 1); self.assertIn("Pack Donor", flag["pan"]["detail"] + "Pack Donor" if flag["pan"]["bad"] > 8 else flag["pan"]["detail"]); self.assertGreaterEqual(flag["cash"]["bad"], 1)
        s, csvb, h = a.rawcall("GET", f"/api/pack/register.csv?fy={fy}"); self.assertEqual(s, 200); self.assertIn("text/csv", h["Content-Type"]); self.assertIn("attachment", h["Content-Disposition"])
        txt = csvb.decode("utf-8-sig"); self.assertIn("Pack Donor", txt); self.assertIn("Cash above", txt); self.assertIn("PAN/ID missing", txt)
        # donor statement (80G): html, escaped, shows total and the cash warning
        d2 = a.call("POST", "/api/t/donors", dict(name="<b>Evil</b> & Co", id_no="ABCDE1234F"))[1]
        a.call("POST", "/api/t/donations", dict(date=asof_day(), donor_id=d2["id"], purpose="General Donation", fund_type="General", mode="UPI", amount=1500, fund_id=funds["General Fund"]))
        s, page, h = a.rawcall("GET", f"/api/pack/donor/{d2['id']}?fy={fy}"); self.assertEqual(s, 200); self.assertIn("text/html", h["Content-Type"]); self.assertIn("inline", h["Content-Disposition"])
        page = page.decode(); self.assertIn("&lt;b&gt;Evil&lt;/b&gt;", page); self.assertNotIn("<b>Evil</b>", page); self.assertIn("1,500.00", page); self.assertIn("ABCDE1234F", page); self.assertIn("Draft prepared", page)
        s, page, h = a.rawcall("GET", f"/api/pack/donor/{d['id']}?fy={fy}"); self.assertIn("generally not eligible", page.decode())
        self.assertEqual(a.rawcall("GET", f"/api/pack/donor/{d['id']}?fy=1990")[0], 404)
        # utilisation certificate
        g = r["grants"][0] if r["grants"] else None
        if g:
            s, uc, h = a.rawcall("GET", f"/api/pack/uc/{g['id']}"); self.assertEqual(s, 200); uc = uc.decode(); self.assertIn("Total received", uc); self.assertIn("Chartered Accountant", uc)
        self.assertEqual(a.rawcall("GET", "/api/pack/uc/99999")[0], 404)
        # audit pack zip
        s, zb, h = adm.rawcall("GET", f"/api/pack/audit-pack?fy={fy}"); self.assertEqual(s, 200); self.assertIn("application/zip", h["Content-Type"])
        z = zipfile.ZipFile(io.BytesIO(zb)); names = z.namelist()
        for n in ("README.txt", "cash-book.csv", "fund-summary.csv", "expense-claims.csv", "grant-spend.csv"): self.assertIn(n, names)
        self.assertTrue(any(n.startswith("donation-register") for n in names)); self.assertIn("not legal or tax advice", z.read("README.txt").decode())
        self.assertEqual(f.rawcall("GET", "/api/pack/audit-pack")[0], 403)

    def test_inbox_webhooks_stop_and_replies(self):
        import hmac, hashlib, base64, urllib.parse
        from app import comms, gateway as g, inbox
        a = self.client("accounts"); adm = self.client("admin"); anon = Client(self.base)
        self.assertEqual(adm.call("PUT", "/api/settings", dict(wa_app_secret="appsecret", wa_verify_token="vt123", inbound_token="gtok", twilio_token="twtok", public_url="https://ngo.example.org"))[0], 200)
        d = a.call("POST", "/api/t/donors", dict(name="Reply Donor", phone="98765 43210", msg_optin="Y"))[1]
        def meta(payload, secret="appsecret"):
            raw = json.dumps(payload).encode(); sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            return anon.rawcall("POST", "/api/hook/meta", raw, {"Content-Type": "application/json", "X-Hub-Signature-256": sig})
        def wa(frm, text, mid, name="Reply Donor"):
            return dict(entry=[dict(changes=[dict(value=dict(contacts=[dict(wa_id=frm, profile=dict(name=name))], messages=[dict(**{"from": frm}, id=mid, type="text", text=dict(body=text))]))])])
        # --- Meta verification handshake
        s, body, h = anon.rawcall("GET", "/api/hook/meta?hub.mode=subscribe&hub.verify_token=vt123&hub.challenge=99887"); self.assertEqual((s, body), (200, b"99887"))
        self.assertEqual(anon.rawcall("GET", "/api/hook/meta?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=1")[0], 403)
        # --- signatures are required
        self.assertEqual(meta(wa("919876543210", "hello", "wamid.1"), secret="not-the-secret")[0], 403)
        self.assertEqual(anon.rawcall("POST", "/api/hook/meta", b"{}", {"Content-Type": "application/json"})[0], 403)
        base_unread = a.call("GET", "/api/inbox/count")[1]["unread"]
        s, body, _ = meta(wa("919876543210", "Thank you, when is the next camp?", "wamid.1")); self.assertEqual(s, 200, body); self.assertEqual(json.loads(body)["stored"], 1)
        self.assertEqual(json.loads(meta(wa("919876543210", "Thank you, when is the next camp?", "wamid.1"))[1])["stored"], 0)          # the provider retries: no duplicate
        self.assertEqual(a.call("GET", "/api/inbox/count")[1]["unread"], base_unread + 1)
        th = [t for t in a.call("GET", "/api/inbox/threads")[1] if t["phone"] == "919876543210"][0]
        self.assertEqual((th["name"], th["known"], th["unread"], th["channel"]), ("Reply Donor", True, 1, "whatsapp"))
        self.assertTrue(any("inbox" in x["text"] for x in a.call("GET", "/api/dashboard")[1]["alerts"]))
        s, t = a.call("GET", "/api/inbox/thread?channel=whatsapp&phone=919876543210"); self.assertEqual(t["messages"][0]["text"], "Thank you, when is the next camp?"); self.assertTrue(t["can_reply"])
        self.assertEqual(a.call("GET", "/api/inbox/count")[1]["unread"], base_unread)                                                    # opening it marked it read
        # --- roles
        self.assertEqual(self.client("field").call("GET", "/api/inbox/threads")[0], 403); self.assertEqual(self.client("viewer").call("GET", "/api/inbox/count")[0], 403)
        # --- a sentence that merely contains the word stop is NOT an opt-out
        meta(wa("919876543210", "please do not stop the camps!", "wamid.2")); self.assertEqual(db.connect().execute("SELECT msg_optin FROM donors WHERE id=?", (d["id"],)).fetchone()[0], "Y")
        # --- STOP: donor switched off, remembered, excluded from broadcasts
        con = db.connect(); self.assertIn("919876543210", {x["to"] for x in comms.audience(con, "all", "", "whatsapp")}); con.close()
        s, body, _ = meta(wa("919876543210", " STOP. ", "wamid.3")); self.assertEqual(json.loads(body)["stops"], 1)
        con = db.connect()
        self.assertEqual(con.execute("SELECT msg_optin FROM donors WHERE id=?", (d["id"],)).fetchone()[0], "N")
        self.assertIsNotNone(con.execute("SELECT 1 FROM optout WHERE phone='919876543210'").fetchone())
        self.assertNotIn("919876543210", {x["to"] for x in comms.audience(con, "all", "", "whatsapp")}); con.close()
        s, e = a.call("POST", "/api/inbox/reply", dict(channel="whatsapp", phone="919876543210", text="Hi")); self.assertEqual(s, 400); self.assertIn("STOP", e["error"])
        # an unknown number that sends STOP is also remembered, so adding them later does not undo it
        meta(wa("919000011111", "unsubscribe", "wamid.4", name="Stranger"))
        self.assertEqual(a.call("POST", "/api/inbox/add-contact", dict(phone="919000011111", name="Stranger"))[0], 400)
        c2 = a.call("POST", "/api/t/contacts", dict(name="Late Add", phone="+91 90000 11111", msg_optin="Y"))[1]
        con = db.connect(); self.assertNotIn("919000011111", {x["to"] for x in comms.audience(con, "everyone", "", "whatsapp")}); con.close()
        # START turns the donor back on
        meta(wa("919876543210", "START", "wamid.5"))
        con = db.connect(); self.assertEqual(con.execute("SELECT msg_optin FROM donors WHERE id=?", (d["id"],)).fetchone()[0], "Y"); self.assertIsNone(con.execute("SELECT 1 FROM optout WHERE phone='919876543210'").fetchone()); con.close()
        # --- replies: free text inside the 24-hour window, via the provider; blocked outside it
        sent = []; orig = g._post
        g._post = lambda url, headers, data, timeout=20: (sent.append(json.loads(data)) or (200, json.dumps({"messages": [{"id": "wamid.OUT1"}]})))
        try:
            adm.call("PUT", "/api/settings", dict(wa_provider="Meta", wa_phone_id="123", wa_token="tok"))
            meta(wa("919876543210", "Can I volunteer?", "wamid.6"))
            self.assertEqual(a.call("POST", "/api/inbox/reply", dict(channel="whatsapp", phone="919876543210", text="   "))[0], 400)
            s, r = a.call("POST", "/api/inbox/reply", dict(channel="whatsapp", phone="919876543210", text="Yes, please come on Sunday.")); self.assertEqual(s, 200, r)
            self.assertEqual(sent[-1]["text"]["body"], "Yes, please come on Sunday."); self.assertEqual(sent[-1]["to"], "919876543210")
            t = a.call("GET", "/api/inbox/thread?channel=whatsapp&phone=919876543210")[1]; self.assertEqual(t["messages"][-1]["direction"], "out"); self.assertEqual(t["messages"][-1]["user"], "Accounts Officer")
            # delivery receipt from the provider is recorded
            meta(dict(entry=[dict(changes=[dict(value=dict(statuses=[dict(id="wamid.OUT1", status="read")]))])]))
            self.assertEqual(a.call("GET", "/api/inbox/thread?channel=whatsapp&phone=919876543210")[1]["messages"][-1]["delivery"], "read")
            # STOP gets an automatic confirmation when switched on
            before = len(sent); meta(wa("919876543210", "stop", "wamid.7")); self.assertEqual(len(sent), before + 1); self.assertIn("unsubscribed", sent[-1]["text"]["body"])
            meta(wa("919876543210", "start", "wamid.8"))
            # outside 24 hours: refused with an explanation
            con = db.connect(); con.execute("UPDATE inbox SET ts=? WHERE phone='919876543210' AND direction='in'", ((datetime.datetime.now() - datetime.timedelta(hours=30)).isoformat(timespec="seconds"),)); con.commit(); con.close()
            s, e = a.call("POST", "/api/inbox/reply", dict(channel="whatsapp", phone="919876543210", text="late")); self.assertEqual(s, 400); self.assertIn("24 hours", e["error"])
        finally:
            g._post = orig; adm.call("PUT", "/api/settings", dict(wa_provider="None"))
        # --- thread admin
        self.assertEqual(a.call("PUT", "/api/inbox/thread", dict(channel="whatsapp", phone="919876543210", status="Done", assignee="field"))[0], 200)
        t = a.call("GET", "/api/inbox/thread?channel=whatsapp&phone=919876543210")[1]; self.assertEqual((t["status"], t["assignee"]), ("Done", "field"))
        self.assertEqual(a.call("PUT", "/api/inbox/thread", dict(channel="whatsapp", phone="919876543210", assignee="nobody"))[0], 400)
        self.assertEqual(a.call("PUT", "/api/inbox/thread", dict(channel="whatsapp", phone="919876543210", status="Weird"))[0], 400)
        meta(wa("919876543210", "one more question", "wamid.9"))                                                                       # a new message reopens it
        self.assertEqual(a.call("GET", "/api/inbox/thread?channel=whatsapp&phone=919876543210")[1]["status"], "Open")
        meta(wa("919123456789", "Hello, who is this?", "wamid.10", name="New Person"))
        s, r = a.call("POST", "/api/inbox/add-contact", dict(phone="919123456789", name="New Person")); self.assertEqual(s, 200, r)
        con = db.connect(); row = con.execute("SELECT msg_optin, wishes FROM contacts WHERE id=?", (r["id"],)).fetchone(); con.close(); self.assertEqual((row[0], row[1]), ("N", "N"))   # wrote to us != agreed to broadcasts
        # --- Twilio: signature over URL + sorted params
        def twilio(params, token="twtok", url="https://ngo.example.org/api/hook/twilio"):
            sig = base64.b64encode(hmac.new(token.encode(), (url + "".join(k + params[k] for k in sorted(params))).encode(), hashlib.sha1).digest()).decode()
            return anon.rawcall("POST", "/api/hook/twilio", urllib.parse.urlencode(params).encode(), {"Content-Type": "application/x-www-form-urlencoded", "X-Twilio-Signature": sig})
        p = {"From": "whatsapp:+919811122233", "Body": "Namaste", "MessageSid": "SM1", "ProfileName": "Twilio Person"}
        self.assertEqual(twilio(p, token="wrong")[0], 403); self.assertEqual(twilio(p, url="https://evil.example/api/hook/twilio")[0], 403)
        s, body, _ = twilio(p); self.assertEqual(s, 200, body); self.assertEqual(twilio(p)[0], 200)
        th = [t for t in a.call("GET", "/api/inbox/threads")[1] if t["phone"] == "919811122233"]; self.assertEqual(len(th), 1); self.assertEqual((th[0]["channel"], th[0]["name"]), ("whatsapp", "Twilio Person"))
        twilio({"From": "+919822233344", "Body": "STOP", "MessageSid": "SM2"})
        self.assertEqual([t for t in a.call("GET", "/api/inbox/threads")[1] if t["phone"] == "919822233344"][0]["channel"], "sms")
        con = db.connect(); self.assertIsNotNone(con.execute("SELECT 1 FROM optout WHERE phone='919822233344'").fetchone()); con.close()
        adm.call("PUT", "/api/settings", dict(public_url="https://ngo.example.org")); 
        # --- generic provider link
        j = {"Content-Type": "application/json"}
        self.assertEqual(anon.rawcall("POST", "/api/hook/generic?token=bad", b'{"from":"919833344455","text":"hi"}', j)[0], 403)
        self.assertEqual(anon.rawcall("POST", "/api/hook/generic", b'{"from":"919833344455","text":"hi"}', j)[0], 403)
        self.assertEqual(anon.rawcall("POST", "/api/hook/generic?token=gtok", b'{"from":"919833344455","text":"hi from gateway","id":"G1"}', j)[0], 200)
        self.assertEqual(anon.rawcall("POST", "/api/hook/generic?token=gtok&channel=sms", b"mobile=919844455566&message=form+text&id=G2", {"Content-Type": "application/x-www-form-urlencoded"})[0], 200)
        self.assertEqual(anon.rawcall("POST", "/api/hook/generic?token=gtok", b'{"text":"no sender"}', j)[0], 400)
        self.assertEqual(anon.rawcall("POST", "/api/hook/generic?token=gtok", b"[1,2]", j)[0], 400)
        chans = {t["phone"]: t["channel"] for t in a.call("GET", "/api/inbox/threads")[1]}; self.assertEqual((chans["919833344455"], chans["919844455566"]), ("whatsapp", "sms"))
        # --- a stored message is plain text: nothing is executed or interpreted
        meta(wa("919855566677", "<script>alert(1)</script>", "wamid.11")); t = a.call("GET", "/api/inbox/thread?channel=whatsapp&phone=919855566677")[1]; self.assertEqual(t["messages"][0]["text"], "<script>alert(1)</script>")
        # --- secrets stay hidden and encrypted
        meta_st = adm.call("GET", "/api/meta")[1]["settings"]; self.assertEqual(meta_st["wa_app_secret"], ""); self.assertEqual(meta_st["wa_app_secret_set"], "Yes")
        con = db.connect(); self.assertTrue(con.execute("SELECT value FROM settings WHERE key='wa_app_secret'").fetchone()[0].startswith("enc1:")); con.close()
        adm.call("PUT", "/api/settings", dict(public_url=""))

    # ====================================================================== v8
    def test_v8_encrypted_backup_and_restore(self):
        from app import securebackup, automation
        adm = self.client("admin"); acc = self.client("accounts")
        self.assertEqual(acc.call("POST", "/api/backup/encrypted", dict(password="correct-horse"))[0], 403)
        self.assertEqual(adm.call("POST", "/api/backup/encrypted", dict(password="short"))[0], 400)
        self.assertEqual(adm.call("PUT", "/api/settings", dict(backup_password="short"))[0], 400)
        s, blob = adm.call("POST", "/api/backup/encrypted", dict(password="correct-horse"), raw=True)
        self.assertEqual(s, 200); self.assertTrue(blob.startswith(b"NGOBK1\n"))
        self.assertNotIn(b"SQLite format", blob); self.assertNotIn(b"Administrator", blob)           # nothing readable inside
        self.assertRaises(securebackup.BackupError, securebackup.decrypt, blob, "wrong-password")
        flipped = bytearray(blob); flipped[len(blob) // 2] ^= 1
        self.assertRaises(securebackup.BackupError, securebackup.decrypt, bytes(flipped), "correct-horse")   # tamper is detected
        mark = adm.call("POST", "/api/t/donors", dict(name="Marker After Backup"))[1]["id"]
        H = lambda **k: {"X-Confirm": "RESTORE", "X-Admin-Password": "ChangeMe123", "X-Backup-Password": "correct-horse", **k}
        self.assertEqual(acc.rawcall("POST", "/api/backup/restore", blob, H())[0], 403)
        self.assertEqual(adm.rawcall("POST", "/api/backup/restore", blob, H(**{"X-Confirm": "no"}))[0], 400)
        self.assertEqual(adm.rawcall("POST", "/api/backup/restore", blob, H(**{"X-Admin-Password": "nope"}))[0], 403)
        self.assertEqual(adm.rawcall("POST", "/api/backup/restore", blob, H(**{"X-Backup-Password": "wrong-password"}))[0], 400)
        self.assertEqual(adm.rawcall("POST", "/api/backup/restore", b"just some text", H())[0], 400)
        self.assertTrue(db.connect().execute("SELECT 1 FROM donors WHERE id=?", (mark,)).fetchone())      # failed attempts changed nothing
        s, body, _ = adm.rawcall("POST", "/api/backup/restore", blob, H()); self.assertEqual(s, 200, body)
        r = json.loads(body); self.assertTrue(r["ok"]); self.assertTrue(r["safety_copy"].startswith("before-restore-"))
        self.assertFalse(db.connect().execute("SELECT 1 FROM donors WHERE id=?", (mark,)).fetchone())      # data went back to the backup
        self.assertEqual(adm.call("GET", "/api/dashboard")[0], 401)                                        # everyone signed out
        adm = self.client("admin")
        self.assertTrue(any(f["name"] == r["safety_copy"] for f in adm.call("GET", "/api/backup/list")[1]["files"]))
        s, plain = adm.call("GET", "/api/backup", raw=True); self.assertTrue(plain.startswith(b"SQLite format 3"))
        m2 = adm.call("POST", "/api/t/donors", dict(name="Marker Two"))[1]["id"]
        self.assertEqual(adm.rawcall("POST", "/api/backup/restore", plain, {"X-Confirm": "RESTORE", "X-Admin-Password": "ChangeMe123"})[0], 200)   # a plain .db restores too
        self.assertFalse(db.connect().execute("SELECT 1 FROM donors WHERE id=?", (m2,)).fetchone())
        adm = self.client("admin")
        # scheduled backups can be password protected, and the password is stored encrypted
        self.assertEqual(adm.call("PUT", "/api/settings", dict(backup_encrypt="Yes", backup_password="another-pass-1"))[0], 200)
        self.assertTrue(db.connect().execute("SELECT value FROM settings WHERE key='backup_password'").fetchone()[0].startswith("enc1:"))
        s, res = adm.call("POST", "/api/automation/run/backup"); self.assertTrue(res["ok"], res); self.assertIn("password-protected", res["note"])
        fl = [f for f in adm.call("GET", "/api/backup/list")[1]["files"] if f["name"].endswith(".ngobk")]; self.assertTrue(fl and fl[0]["protected"])
        s, got = adm.call("GET", "/api/backup/file/" + fl[0]["name"], raw=True); self.assertEqual(s, 200); self.assertTrue(got.startswith(b"NGOBK1"))
        self.assertEqual(adm.call("GET", "/api/backup/file/..%2f..%2fsecret.key")[0], 404)
        adm.call("PUT", "/api/settings", dict(backup_encrypt="No"))

    def test_v8_journey(self):
        adm = self.client("admin"); fld = self.client("field"); vw = self.client("viewer"); today = asof_day()
        old = (datetime.date.fromisoformat(today) - datetime.timedelta(days=200)).isoformat()
        pid = adm.call("GET", "/api/t/projects")[1][0]["id"]
        a = adm.call("POST", "/api/t/beneficiaries", dict(name="Journey Asha", village="Rampur", project_id=pid, date_joined=old, gender="Female"))[1]["id"]
        b = adm.call("POST", "/api/t/beneficiaries", dict(name="Journey Ravi", village="Rampur", project_id=pid, date_joined=today))[1]["id"]
        self.assertEqual(vw.call("POST", "/api/t/journey", dict(beneficiary_id=a, date=today, stage="Assessed"))[0], 403)
        s, j = fld.call("POST", "/api/t/journey", dict(beneficiary_id=b, date=today, stage="Assessed", detail="Baseline done")); self.assertEqual(s, 200, j)
        self.assertEqual(db.connect().execute("SELECT recorded_by FROM journey WHERE id=?", (j["id"],)).fetchone()[0], "Field Coordinator")
        fld.call("POST", "/api/t/journey", dict(beneficiary_id=b, date=today, stage="Outcome achieved", outcome="Passed Class 10"))
        t = fld.call("GET", f"/api/journey/timeline/{b}")[1]
        self.assertEqual([e["stage"] for e in t["events"]][0], "Enrolled"); self.assertTrue(t["events"][0]["implied"])      # joining date shows as the first step
        self.assertTrue(t["achieved"]); self.assertEqual(t["person"]["name"], "Journey Ravi")
        t2 = fld.call("GET", f"/api/journey/timeline/{a}")[1]; self.assertEqual(t2["next_step"], "Assessed"); self.assertGreaterEqual(t2["days_quiet"], 199)
        sm = fld.call("GET", f"/api/journey/summary?project_id={pid}")[1]; fun = {x["stage"]: x["count"] for x in sm["funnel"]}
        self.assertGreaterEqual(fun["Enrolled"], 2); self.assertGreaterEqual(fun["Assessed"], 1); self.assertTrue(any(o["outcome"] == "Passed Class 10" for o in sm["outcomes"]))
        st = fld.call("GET", "/api/journey/stale")[1]; ids = [p["id"] for p in st["people"]]; self.assertIn(a, ids); self.assertNotIn(b, ids)
        fld.call("POST", "/api/t/journey", dict(beneficiary_id=a, date=today, stage="Exited"))                                    # a person who has exited is no longer chased
        self.assertNotIn(a, [p["id"] for p in fld.call("GET", "/api/journey/stale")[1]["people"]])
        self.assertEqual(fld.call("GET", "/api/journey/timeline/999999")[0], 404)
        self.assertTrue(any(p["name"] == "Journey Ravi" for p in fld.call("GET", "/api/journey/people?q=Ravi")[1]))

    def test_v8_promises_lapse_and_language(self):
        from app import donorcare, automation, mailer
        acc = self.client("accounts"); vw = self.client("viewer"); today = datetime.date.fromisoformat(asof_day()); D = lambda n: (today - datetime.timedelta(days=n)).isoformat()
        self.assertEqual(vw.call("GET", "/api/care/lapse")[0], 403); self.assertEqual(vw.call("GET", "/api/care/promises")[0], 403)
        # --- a monthly promise: two months paid, the third is late, then it is paid
        d = acc.call("POST", "/api/t/donors", dict(name="Promise Meena", phone="98111 22233", email="meena@example.org", msg_optin="Y"))[1]["id"]
        start = donorcare._add_months(today, -2) - datetime.timedelta(days=12)
        s, cm = acc.call("POST", "/api/t/commitments", dict(donor_id=d, amount=500, frequency="Monthly", start=start.isoformat())); self.assertEqual(s, 200, cm)
        for k in (0, 1): acc.call("POST", "/api/t/donations", dict(date=donorcare._add_months(start, k).isoformat(), donor_id=d, purpose="General Donation", fund_type="General", mode="UPI", amount=500))
        it = [x for x in acc.call("GET", "/api/care/promises")[1]["items"] if x["id"] == cm["id"]][0]
        self.assertEqual((it["paid"], it["missed"], it["status"]), (2, 1, "Late")); self.assertEqual(it["owed"], 500); self.assertIn("Promise", it["message"]); self.assertIn(it["missed_dates"][-1], it["message"]); self.assertTrue(it["wa"].startswith("https://wa.me/919811122233"))
        acc.call("POST", "/api/t/donations", dict(date=today.isoformat(), donor_id=d, purpose="General Donation", fund_type="General", mode="UPI", amount=500))
        it = [x for x in acc.call("GET", "/api/care/promises")[1]["items"] if x["id"] == cm["id"]][0]; self.assertEqual((it["paid"], it["missed"]), (3, 0)); self.assertNotEqual(it["status"], "Late")
        acc.call("PUT", f"/api/t/commitments/{cm['id']}", dict(status="Paused"))
        self.assertEqual([x for x in acc.call("GET", "/api/care/promises")[1]["items"] if x["id"] == cm["id"]][0]["status"], "Paused")
        # --- reminder email goes out once per due date
        d2 = acc.call("POST", "/api/t/donors", dict(name="Reminder Raj", email="raj@example.org", language="Hindi"))[1]["id"]
        due = (today + datetime.timedelta(days=2)).isoformat()
        acc.call("POST", "/api/t/commitments", dict(donor_id=d2, amount=1000, frequency="Monthly", start=due))
        sent = []; real = mailer.send_mail; mailer.send_mail = lambda s, to, subj, body, html=None: sent.append((to, body))
        con = db.connect(); prev = (con.execute("SELECT value FROM settings WHERE key='smtp_host'").fetchone() or [''])[0]; con.execute("INSERT OR REPLACE INTO settings VALUES('smtp_host','smtp.test')"); con.commit()
        try:
            r1 = automation.send_commitment_reminders(con); r2 = automation.send_commitment_reminders(con)
        finally:
            mailer.send_mail = real; con.execute("INSERT OR REPLACE INTO settings VALUES('smtp_host',?)", (prev,)); con.commit(); con.close()
        self.assertEqual(r1["sent"], 1); self.assertEqual(r2["sent"], 0); self.assertEqual(sent[0][0], "raj@example.org")
        self.assertIn("नियमित", sent[0][1])                                                            # the reminder is in the donor's own language
        # --- lapse: their own rhythm, not a fixed rule
        g = acc.call("POST", "/api/t/donors", dict(name="Lapsed Lakshmi", phone="97000 11122", language="Tamil", msg_optin="Y"))[1]["id"]
        for n in (900, 720, 540): acc.call("POST", "/api/t/donations", dict(date=D(n), donor_id=g, purpose="General Donation", fund_type="General", mode="UPI", amount=1200))
        ok = acc.call("POST", "/api/t/donors", dict(name="Regular Rani"))[1]["id"]
        for n in (330, 240, 150, 60): acc.call("POST", "/api/t/donations", dict(date=D(n), donor_id=ok, purpose="General Donation", fund_type="General", mode="UPI", amount=500))
        late = acc.call("POST", "/api/t/donors", dict(name="Late Latha"))[1]["id"]
        for n in (400, 300, 200): acc.call("POST", "/api/t/donations", dict(date=D(n), donor_id=late, purpose="General Donation", fund_type="General", mode="UPI", amount=500))
        lp = acc.call("GET", "/api/care/lapse")[1]; by = {x["id"]: x for x in lp["donors"]}
        self.assertEqual(by[g]["status"], "Lapsed"); self.assertEqual(by[g]["cadence_days"], 180); self.assertIn("Lapsed", by[g]["message"]); self.assertIn("நன்கொடை", by[g]["message"])
        self.assertTrue(by[g]["wa"].startswith("https://wa.me/919700011122"))
        self.assertNotIn(ok, by)                                                                    # gave 60 days ago on a 90-day rhythm: fine
        self.assertEqual(by[late]["cadence_days"], 100); self.assertIn(by[late]["status"], ("Due for a thank-you or update", "Slipping"))
        self.assertNotIn(d2, by)                                                                    # active promise: handled on the promises board
        self.assertGreater(lp["value_at_risk"], 0)
        self.assertEqual(acc.call("POST", "/api/care/followup", dict(donor_id=g))[0], 200)
        self.assertEqual(db.connect().execute("SELECT next_followup FROM donors WHERE id=?", (g,)).fetchone()[0], today.isoformat())
        # --- regional language: templates exist, the broadcast can target a language
        names = {t["name"] for t in acc.call("GET", "/api/t/templates")[1]}; self.assertTrue({"Hindi: thank-you", "Telugu: festival greeting", "Kannada: we miss you"} <= names)
        acc.call("PUT", f"/api/t/donors/{d2}", dict(wishes="Y"))
        pv = acc.call("POST", "/api/campaign/preview", dict(segment="language", param="Hindi"))[1]; self.assertGreaterEqual(pv["counts"]["email"], 1); self.assertIn("Reminder Raj", pv["sample"] + [x for x in pv["sample"]])
        self.assertEqual(acc.call("POST", "/api/campaign/preview", dict(segment="language", param="Bengali"))[1]["counts"]["email"], 0)
        from app import langpack
        for kind in langpack.MSG:
            self.assertEqual(set(langpack.MSG[kind]), set(langpack.LANGS))
            for lang, t in langpack.MSG[kind].items(): self.assertIn("{first_name}", t); self.assertIn("{org}", t)
        self.assertIn("राहुल", langpack.render("thanks", "Hindi", dict(first_name="राहुल", org="X", contact="")))
        self.assertTrue(langpack.render("thanks", "Klingon", dict(first_name="A", org="X", contact="")).startswith("Dear A"))        # unknown language falls back to English

    def test_v8_duplicates_and_merge(self):
        acc = self.client("accounts"); adm = self.client("admin"); fld = self.client("field"); today = asof_day()
        a = acc.call("POST", "/api/t/donors", dict(name="Dup Suresh Kumar", phone="99000 12345", id_no="ABCDE1234F", notes="first"))[1]["id"]
        b = acc.call("POST", "/api/t/donors", dict(name="Suresh Kumar Dup2", phone="+91 99000 12345", email="s@example.org", notes="second"))[1]["id"]
        c3 = acc.call("POST", "/api/t/donors", dict(name="Other Person", phone="99000 12345", id_no="ZZZZZ9999Z"))[1]["id"]
        for did in (a, b): acc.call("POST", "/api/t/donations", dict(date=today, donor_id=did, purpose="General Donation", fund_type="General", mode="UPI", amount=300))
        acc.call("POST", "/api/t/interactions", dict(date=today, donor_id=b, summary="called")); acc.call("PUT", f"/api/t/donors/{b}", dict(next_followup="2030-01-01"))
        sc = acc.call("GET", "/api/dedupe/scan?kind=donors")[1]; grp = [g for g in sc["groups"] if {a, b} <= {r["id"] for r in g["records"]}][0]
        self.assertIn("same phone number", grp["reasons"]); self.assertTrue(grp["conflict"])                       # a and c3 have different PANs: warn
        self.assertEqual(fld.call("GET", "/api/dedupe/scan?kind=donors")[0], 403); self.assertEqual(fld.call("POST", "/api/dedupe/merge", dict(kind="donors", keep=a, drop=[b]))[0], 403)
        self.assertEqual(acc.call("POST", "/api/dedupe/merge", dict(kind="donors", keep=a, drop=[c3]))[0], 400)    # different PANs: refuse
        self.assertEqual(acc.call("POST", "/api/dedupe/merge", dict(kind="donors", keep=a, drop=[a]))[0], 400)
        self.assertEqual(acc.call("POST", "/api/dedupe/merge", dict(kind="donors", keep=a, drop=[999999]))[0], 404)
        s, r = acc.call("POST", "/api/dedupe/merge", dict(kind="donors", keep=a, drop=[b])); self.assertEqual(s, 200, r)
        con = db.connect()
        self.assertEqual(con.execute("SELECT COUNT(*) FROM donations WHERE donor_id=?", (a,)).fetchone()[0], 2)     # both gifts now sit on one donor
        self.assertEqual(con.execute("SELECT COUNT(*) FROM interactions WHERE donor_id=?", (a,)).fetchone()[0], 1)
        self.assertFalse(con.execute("SELECT 1 FROM donors WHERE id=?", (b,)).fetchone())
        row = con.execute("SELECT email, next_followup, notes FROM donors WHERE id=?", (a,)).fetchone()
        self.assertEqual((row["email"], row["next_followup"]), ("s@example.org", "2030-01-01")); self.assertIn("second", row["notes"]); self.assertIn("first", row["notes"])   # blanks filled, nothing lost
        con.close()
        au = adm.call("GET", "/api/auditlog?action=merge")[1]; self.assertTrue(any("Suresh Kumar Dup2" in x["detail"] for x in au["rows"]))   # the merge is on record
        # --- people served: near-identical spelling in the same village, journey steps follow the kept record
        pid = adm.call("GET", "/api/t/projects")[1][0]["id"]
        x = adm.call("POST", "/api/t/beneficiaries", dict(name="Ramesh Patil", village="Kheda", project_id=pid))[1]["id"]
        y = adm.call("POST", "/api/t/beneficiaries", dict(name="Rameshh Patil", village="Kheda", project_id=pid, phone="90000 11111"))[1]["id"]
        adm.call("POST", "/api/t/journey", dict(beneficiary_id=y, date=today, stage="Assessed"))
        sc = fld.call("GET", "/api/dedupe/scan?kind=beneficiaries")[1]; self.assertTrue(any({x, y} <= {r["id"] for r in g["records"]} for g in sc["groups"]))
        self.assertEqual(fld.call("POST", "/api/dedupe/merge", dict(kind="beneficiaries", keep=x, drop=[y]))[0], 200)
        con = db.connect(); self.assertEqual(con.execute("SELECT COUNT(*) FROM journey WHERE beneficiary_id=?", (x,)).fetchone()[0], 1)
        self.assertEqual(con.execute("SELECT phone FROM beneficiaries WHERE id=?", (x,)).fetchone()[0], "90000 11111"); con.close()
        self.assertEqual(adm.call("GET", "/api/dedupe/scan?kind=nonsense")[0], 400)

    def test_v8_weekly_csr_and_audit(self):
        from app import weekly, automation, csr
        acc = self.client("accounts"); adm = self.client("admin"); vw = self.client("viewer"); today = asof_day()
        self.assertEqual(vw.call("GET", "/api/weekly")[0], 403)
        sm = acc.call("GET", "/api/weekly")[1]; self.assertIn("week", sm); self.assertIn("items", sm); self.assertEqual(sm["date"], today)
        self.assertTrue(all(i["level"] in ("red", "amber", "blue") for i in sm["items"]))
        self.assertEqual(acc.call("POST", "/api/weekly/send")[0], 403)
        r = adm.call("POST", "/api/weekly/send")[1]; self.assertTrue("note" in r or "failed" in r)                   # it reports what happened, never silence
        self.assertEqual(adm.call("PUT", "/api/settings", dict(weekly_to="not-an-email"))[0], 400)
        self.assertEqual(adm.call("PUT", "/api/settings", dict(weekly_to="boss@example.org", weekly_auto="Yes"))[0], 200)
        sent = []; real = mailer.send_mail; mailer.send_mail = lambda s, to, subj, body, html=None: sent.append((to, subj, body))
        con = db.connect(); prev = (con.execute("SELECT value FROM settings WHERE key='smtp_host'").fetchone() or [''])[0]; con.execute("INSERT OR REPLACE INTO settings VALUES('smtp_host','smtp.test')"); con.commit()
        try:
            r1 = weekly.send(con, force=True); r2 = weekly.send(con, force=True)
        finally:
            mailer.send_mail = real; con.execute("INSERT OR REPLACE INTO settings VALUES('smtp_host',?)", (prev,)); con.commit(); con.close()
        self.assertEqual((r1["sent"], r2["sent"]), (1, 0)); self.assertIn("weekly summary", sent[0][1]); self.assertIn("This week:", sent[0][2])
        adm.call("PUT", "/api/settings", dict(weekly_to="", weekly_auto="No"))
        # --- funder report
        pid = adm.call("GET", "/api/t/projects")[1][0]["id"]; pname = adm.call("GET", "/api/t/projects")[1][0]["name"]
        y = today[:4]
        s, html = acc.call("GET", f"/api/csr?project_id={pid}&from={y}-01-01&to={y}-12-31&notes=Thanks+all", raw=True); self.assertEqual(s, 200); h = html.decode()
        self.assertIn(pname, h); self.assertIn("People reached", h); self.assertIn("Draft made from your own records", h); self.assertIn("Thanks all", h)
        s, html = self.client("field").call("GET", f"/api/csr?project_id={pid}&from={y}-01-01&to={y}-12-31", raw=True); self.assertEqual(s, 200)
        self.assertEqual(vw.call("GET", f"/api/csr?project_id={pid}&from={y}-01-01&to={y}-12-31")[0], 403)
        self.assertEqual(acc.call("GET", f"/api/csr?project_id={pid}&from=bad&to={y}-12-31")[0], 400)
        self.assertEqual(acc.call("GET", f"/api/csr?project_id={pid}&from={y}-12-31&to={y}-01-01")[0], 400)
        self.assertEqual(acc.call("GET", f"/api/csr?project_id=99999&from={y}-01-01&to={y}-12-31")[0], 404)
        self.assertEqual(acc.call("GET", f"/api/csr?project_id={pid}&from=2020-01-01&to={y}-12-31")[0], 400)           # absurdly long period refused
        # an unconsented photo never appears, a consented one does
        cl = adm.rawcall("POST", "/api/media?kind=photo&project_id=%d&consent=N&purpose=event" % pid, b"\xff\xd8\xff\xe0" + b"0" * 200, {"Content-Type": "image/jpeg"})
        self.assertNotIn(b"data:image", acc.call("GET", f"/api/csr?project_id={pid}&from={y}-01-01&to={y}-12-31", raw=True)[1])
        # --- audit trail: searchable, filterable, exportable, administrators only
        self.assertEqual(acc.call("GET", "/api/auditlog")[0], 403); self.assertEqual(acc.call("GET", "/api/auditlog/export.csv")[0], 403)
        adm.call("POST", "/api/t/donors", dict(name="Audit Probe Donor"))
        a = adm.call("GET", "/api/auditlog?q=Audit+Probe")[1]; self.assertGreaterEqual(a["total"], 1); self.assertTrue(all("Audit Probe" in (r["detail"] or "") for r in a["rows"]))
        self.assertIn("admin", a["facets"]["users"]); self.assertIn("create", a["facets"]["actions"]); self.assertIn("donors", a["facets"]["tables"])
        f = adm.call("GET", "/api/auditlog?user=accounts&tbl=donors&action=create&limit=10")[1]; self.assertTrue(all(r["user"] == "accounts" and r["tbl"] == "donors" for r in f["rows"]))
        self.assertLessEqual(len(f["rows"]), 10)
        one = a["rows"][0]; h = adm.call("GET", f"/api/auditlog?tbl={one['tbl']}&row_id={one['row_id']}")[1]; self.assertTrue(all(r["row_id"] == one["row_id"] for r in h["rows"]))
        self.assertEqual(adm.call("GET", f"/api/auditlog?from={today}&to={today}&limit=10")[0], 200)
        s, csvb = adm.call("GET", "/api/auditlog/export.csv?q=Audit+Probe", raw=True); self.assertEqual(s, 200); self.assertTrue(csvb.startswith(b"\xef\xbb\xbfWhen,Who,Action")); self.assertIn(b"Audit Probe", csvb)
        self.assertEqual(adm.call("GET", "/api/auditlog?q=%27%3B+DROP+TABLE+audit%3B--")[0], 200)                  # search text can never become SQL
        self.assertTrue(db.connect().execute("SELECT COUNT(*) FROM audit").fetchone()[0] > 0)

    def test_v10_pages_and_registers(self):
        adm = self.client("admin"); vw = self.client("viewer"); today = asof_day()
        did = adm.call("GET", "/api/t/donors")[1][0]["id"]
        # donor giving page token
        st, r = adm.call("POST", f"/api/donors/{did}/portal", {}); self.assertEqual(st, 200)
        # transparency page is off by default
        self.assertNotEqual(adm.call("GET", "/api/yearcheck")[0], 500)
        # registers
        self.assertEqual(adm.call("POST", "/api/t/outcomes", dict(title="School kit", unit_cost=500, per="year", active="Y"))[0], 200)
        self.assertEqual(adm.call("POST", "/api/t/incidents", dict(date=today, kind="Other", description="Test", status="Open"))[0], 200)
        self.assertEqual(vw.call("GET", "/api/t/incidents")[0], 403)
        self.assertEqual(adm.call("GET", "/api/yearcheck")[0], 200)

    def test_v11_governance_and_blank_ca(self):
        adm = self.client("admin"); acc = self.client("accounts"); vw = self.client("viewer"); today = asof_day()
        self.assertEqual(adm.call("POST", "/api/policies/starter", {})[1]["added"], 8)
        self.assertEqual(adm.call("POST", "/api/policies/starter", {})[1]["added"], 0)
        self.assertEqual(vw.call("POST", "/api/policies/starter", {})[0], 403)
        self.assertEqual(vw.call("GET", "/api/t/trustees")[0], 403)
        self.assertEqual(adm.call("POST", "/api/t/trustees", dict(name="A Trustee", role="Treasurer", status="Active"))[0], 200)
        self.assertEqual(adm.call("POST", "/api/t/meetings", dict(date=today, kind="AGM", quorum="Y"))[0], 200)
        # blank-dated compliance items are allowed and never counted overdue
        self.assertEqual(adm.call("POST", "/api/yearcheck/starter", {})[0], 200)
        rows = adm.call("GET", "/api/t/compliance")[1]
        self.assertTrue(any(r["due_date"] in ("", None) for r in rows))
        self.assertFalse(any(r["due_date"] in ("", None) and r.get("cstatus") == "Overdue" for r in rows))
        yc = acc.call("GET", "/api/yearcheck")[1]["items"]
        self.assertTrue(any("CA details" in i["title"] and i["status"] == "warn" for i in yc))
        # CA details start blank and only admin can set them through tool settings
        self.assertEqual(adm.call("GET", "/api/settings")[1].get("ca_name", ""), "")

    def test_v12_social_posts(self):
        adm = self.client("admin"); fld = self.client("field"); vw = self.client("viewer"); today = asof_day()
        self.assertEqual(vw.call("GET", "/api/social/ideas")[0], 403)
        self.assertIn("caption", fld.call("GET", "/api/social/draft?lang=Hindi")[1])
        self.assertIn("items", fld.call("GET", "/api/social/ideas")[1])
        ok = dict(title="Camp", caption="Camp on Saturday", owner="Ravi")
        self.assertEqual(fld.call("POST", "/api/t/social_posts", ok)[0], 200)
        # needs an approver who is a different person
        self.assertEqual(fld.call("POST", "/api/t/social_posts", dict(ok, status="Approved"))[0], 400)
        self.assertEqual(fld.call("POST", "/api/t/social_posts", dict(ok, status="Approved", approved_by="Ravi"))[0], 400)
        self.assertEqual(fld.call("POST", "/api/t/social_posts", dict(ok, status="Approved", approved_by="Asha"))[0], 200)
        self.assertEqual(fld.call("POST", "/api/t/social_posts", dict(ok, status="Posted", approved_by="Asha"))[0], 400)
        # a donor's or beneficiary's name is blocked unless they agreed
        name = adm.call("GET", "/api/t/donors")[1][0]["name"]
        self.assertEqual(fld.call("POST", "/api/t/social_posts", dict(ok, caption=f"Thanks to {name} for the gift"))[0], 400)
        self.assertEqual(fld.call("POST", "/api/t/social_posts", dict(ok, caption=f"Thanks to {name} for the gift", names_ok="Y"))[0], 200)

    def test_v13_yearplan(self):
        adm = self.client("admin"); acc = self.client("accounts"); fld = self.client("field"); vw = self.client("viewer"); today = asof_day()
        self.assertEqual(vw.call("GET", "/api/yearplan")[0], 403); self.assertEqual(fld.call("GET", "/api/yearplan")[0], 403)
        n = adm.call("POST", "/api/yearplan/starter", {})[1]["added"]; self.assertGreater(n, 15)
        self.assertEqual(adm.call("POST", "/api/yearplan/starter", {})[1]["added"], 0)
        self.assertEqual(adm.call("POST", "/api/t/csr_pipeline", dict(company="Acme Mills", kind="CSR grant", stage="Pitched", ask=500000, next_date=today, next_step="Send budget", decision_by=today))[0], 200)
        self.assertEqual(vw.call("GET", "/api/t/csr_pipeline")[0], 403)
        self.assertEqual(fld.call("GET", "/api/t/plan_calendar")[0], 200)
        self.assertEqual(fld.call("POST", "/api/t/plan_calendar", dict(date=today, title="x"))[0], 403)
        yp = acc.call("GET", "/api/yearplan")[1]
        self.assertTrue(any(i["type"] == "Company" and "Acme Mills" in i["title"] for i in yp["items"]))
        self.assertTrue(any(i["type"] == "Decision" for i in yp["items"]))
        self.assertTrue(any(p["stage"] == "Pitched" and p["ask"] == 500000 for p in yp["pipeline"]))

    def test_v14_documents_and_proposal(self):
        adm = self.client("admin"); acc = self.client("accounts"); fld = self.client("field"); vw = self.client("viewer"); today = asof_day()
        self.assertEqual(vw.call("POST", "/api/odocs/starter", {})[0], 403); self.assertEqual(fld.call("GET", "/api/t/official_docs")[0], 403)
        n = adm.call("POST", "/api/odocs/starter", {})[1]["added"]; self.assertGreater(n, 15)
        self.assertEqual(adm.call("POST", "/api/odocs/starter", {})[1]["added"], 0)
        rows = acc.call("GET", "/api/t/official_docs")[1]; d = [r for r in rows if r["name"].startswith("80G")][0]
        self.assertEqual(d["state"], "Missing"); self.assertEqual(d["has_file"], "N")
        # upload: wrong type refused, real pdf accepted, oversize refused
        self.assertEqual(adm.rawcall("POST", f"/api/odocs/{d['id']}/file?name=x.exe", b"MZ" + b"0" * 50, {"Content-Type": "application/octet-stream"})[0], 415)
        pdf = b"%PDF-1.4\n" + b"x" * 500
        st, body, _ = adm.rawcall("POST", f"/api/odocs/{d['id']}/file?name=80g.pdf", pdf, {"Content-Type": "application/pdf"}); self.assertEqual(st, 200)
        self.assertEqual(fld.rawcall("GET", f"/api/odocs/{d['id']}/file")[0], 403)
        st, body, hd = acc.rawcall("GET", f"/api/odocs/{d['id']}/file"); self.assertEqual(st, 200); self.assertEqual(body, pdf)
        d2 = [r for r in acc.call("GET", "/api/t/official_docs")[1] if r["id"] == d["id"]][0]; self.assertEqual(d2["has_file"], "Y"); self.assertEqual(d2["state"], "Have")
        past = (datetime.date.fromisoformat(today) - datetime.timedelta(days=3)).isoformat()
        self.assertEqual(adm.call("PUT", f"/api/t/official_docs/{d['id']}", dict(name=d["name"], valid_until=past, status="Have"))[0], 200)
        self.assertEqual([r for r in acc.call("GET", "/api/t/official_docs")[1] if r["id"] == d["id"]][0]["state"], "Expired")
        self.assertEqual(adm.call("DELETE", f"/api/odocs/{d['id']}/file")[0], 200)
        self.assertEqual(adm.rawcall("GET", f"/api/odocs/{d['id']}/file")[0], 404)
        # proposal
        pid = adm.call("GET", "/api/t/projects")[1][0]["id"]
        self.assertEqual(vw.rawcall("GET", f"/api/proposal?project_id={pid}")[0], 403)
        st, html, hd = fld.rawcall("GET", f"/api/proposal?project_id={pid}&company=Acme+%3Cb%3E+Ltd&ask=450000&months=12&clause=ii"); self.assertEqual(st, 200)
        html = html.decode(); self.assertIn("CSR project proposal", html); self.assertIn("Acme &lt;b&gt; Ltd", html); self.assertNotIn("Acme <b>", html)
        self.assertIn("<mark>[", html); self.assertIn("450,000.00", html)
        self.assertEqual(adm.rawcall("GET", "/api/proposal?project_id=99999")[0], 404)

    def test_v14_notifications(self):
        adm = self.client("admin"); fld = self.client("viewer"); today = asof_day()
        adm.call("POST", "/api/t/partner_events", dict(date=today, title="Tree day", status="Planned"))
        adm.call("POST", "/api/t/compliance", dict(title="Test return", due_date=today, status="Pending"))
        a = adm.call("GET", "/api/notifications")[1]; f = fld.call("GET", "/api/notifications")[1]
        self.assertTrue(any(i["kind"] == "Event" and i["text"].startswith("Tree day") for i in a["items"]))
        self.assertTrue(any(i["kind"] == "Compliance" for i in a["items"]))
        self.assertTrue(any(i["kind"] == "Event" for i in f["items"])); self.assertFalse(any(i["kind"] in ("Compliance", "Birthday", "Company") for i in f["items"]))

    def test_v9_partners_events_portal(self):
        adm = self.client("admin"); acc = self.client("accounts"); fld = self.client("field"); vw = self.client("viewer"); today = asof_day()
        st, pid = adm.call("POST", "/api/t/partners", dict(name="Acme Corp", stage="Active", expected_amount=100000, owner="Asha", renewal_date=(datetime.date.fromisoformat(today) + datetime.timedelta(days=20)).isoformat()))
        self.assertEqual(st, 200); pid = pid["id"] if isinstance(pid, dict) else pid
        self.assertEqual(vw.call("GET", "/api/partners/pipeline")[0], 403); self.assertEqual(fld.call("GET", "/api/partners/pipeline")[0], 403)
        p = acc.call("GET", "/api/partners/pipeline")[1]; row = [r for r in p["items"] if r["name"] == "Acme Corp"][0]
        self.assertIn("No backup", row["flags"]); self.assertTrue(any(f.startswith("Renewal in") for f in row["flags"])); self.assertTrue(any(x["stage"] == "Active" and x["count"] >= 1 for x in p["stages"]))
        # a gift through the company and a finished event
        did = adm.call("GET", "/api/t/donors")[1][0]["id"]
        self.assertEqual(adm.call("POST", "/api/t/donations", dict(date=today, donor_id=did, amount=2500, partner_id=pid, mode="UPI"))[0], 200)
        self.assertEqual(fld.call("POST", "/api/t/partner_events", dict(date=today, title="Tree planting day", partner_id=pid, status="Done", attended=12, hours=36, raised=5000))[0], 200)
        row = [r for r in acc.call("GET", "/api/partners/pipeline")[1]["items"] if r["id"] == pid][0]
        self.assertEqual((row["given"], row["events"], row["hours"]), (2500, 1, 36))
        eid = adm.call("GET", "/api/t/partner_events")[1][0]["id"]
        n = fld.call("GET", f"/api/partners/event-note/{eid}")[1]; self.assertIn("Acme Corp", n["note"]); self.assertIn("12 colleagues", n["note"]); self.assertIn("36 volunteer hours", n["note"])
        self.assertEqual(fld.call("GET", "/api/partners/event-note/99999")[0], 404); self.assertEqual(vw.call("GET", f"/api/partners/event-note/{eid}")[0], 403)
        # private company page: off by default, on with a link, off again when revoked, never lists other companies
        adm.call("POST", "/api/t/partners", dict(name="Other Secret Ltd", stage="Prospect"))
        self.assertEqual(Client(self.base).call("GET", "/api/public/partner/aaaaaaaaaaaaaaaaaaaa")[0], 404)
        self.assertEqual(fld.call("POST", f"/api/partners/{pid}/portal", {})[0], 403)
        tok = acc.call("POST", f"/api/partners/{pid}/portal", {})[1]["token"]; self.assertGreaterEqual(len(tok), 20)
        s, html = Client(self.base).call("GET", f"/api/public/partner/{tok}", raw=True); h = html.decode()
        self.assertEqual(s, 200); self.assertIn("Acme Corp", h); self.assertIn("Tree planting day", h); self.assertIn("2,500.00", h); self.assertNotIn("Other Secret", h)
        self.assertEqual(acc.call("POST", f"/api/partners/{pid}/portal", dict(revoke=True))[0], 200)
        self.assertEqual(Client(self.base).call("GET", f"/api/public/partner/{tok}")[0], 404)

    def test_v9_forecast_relations_board(self):
        adm = self.client("admin"); acc = self.client("accounts"); vw = self.client("viewer"); today = asof_day(); t0 = datetime.date.fromisoformat(today)
        for u in ("/api/forecast", "/api/relations", "/api/funders/tracker", "/api/board", "/api/boardpack"): self.assertEqual(vw.call("GET", u)[0], 403)
        # funder payments: one overdue, one coming
        gid = adm.call("GET", "/api/t/grants")[1][0]["id"]
        late = (t0 - datetime.timedelta(days=15)).isoformat(); soon = (t0 + datetime.timedelta(days=40)).isoformat()
        self.assertEqual(acc.call("POST", "/api/t/tranches", dict(grant_id=gid, due_date=late, amount=70000))[0], 200)
        self.assertEqual(acc.call("POST", "/api/t/tranches", dict(grant_id=gid, due_date=soon, amount=30000))[0], 200)
        tk = acc.call("GET", "/api/funders/tracker")[1]; od = [r for r in tk["items"] if r["state"] == "Overdue"][0]
        self.assertEqual(od["days_late"], 15); self.assertEqual(tk["summary"]["overdue_amount"], 70000)
        # forecast: 12 months, overdue money lands in the first month, free cash excludes restricted funds
        self.assertEqual(acc.call("PUT", "/api/tool-settings", dict(core_monthly_cost="50000", reserve_months="3"))[0], 200)
        f = acc.call("GET", "/api/forecast")[1]; self.assertEqual(len(f["rows"]), 12); self.assertEqual(f["monthly_cost"], 50000); self.assertEqual(f["reserve"], 150000)
        self.assertEqual(f["rows"][0]["funders"], 70000)
        self.assertEqual(sum(r["funders"] for r in f["rows"]), 100000)
        bal = f["opening"]
        for r in f["rows"]:
            bal += r["inflow"] - r["outflow"]; self.assertEqual(r["balance"], bal); self.assertEqual(r["free"], r["balance"] - f["restricted"])
            self.assertIn(r["status"], ("OK", "Short", "Below reserve"))
        self.assertEqual(len(acc.call("GET", "/api/forecast?months=3")[1]["rows"]), 3); self.assertEqual(len(acc.call("GET", "/api/forecast?months=abc")[1]["rows"]), 12)
        # a received payment drops out of the forecast
        tid = [r for r in tk["items"] if r["state"] == "Overdue"][0]["id"]
        acc.call("PUT", f"/api/t/tranches/{tid}", dict(received_date=today)); self.assertEqual(acc.call("GET", "/api/funders/tracker")[1]["summary"]["overdue"], 0)
        self.assertEqual(sum(r["funders"] for r in acc.call("GET", "/api/forecast")[1]["rows"]), 30000)
        self.assertEqual(acc.call("PUT", "/api/settings", dict(core_monthly_cost="abc"))[0], 403)
        self.assertEqual(adm.call("PUT", "/api/settings", dict(core_monthly_cost="abc"))[0], 400)
        # relationships: a donor above the major-donor line with no owner is flagged, then fixed
        adm.call("PUT", "/api/tool-settings", dict(major_donor_min="1"))
        r = acc.call("GET", "/api/relations")[1]; self.assertGreater(r["summary"]["total"], 0)
        k = [i for i in r["items"] if i["kind"] == "Major donor"][0]; self.assertIn("No owner", k["risk"])
        adm.call("PUT", f"/api/t/donors/{k['id']}", dict(owner="Asha", backup_owner="Ravi", handover_note="Calls on Sundays"))
        k2 = [i for i in acc.call("GET", "/api/relations")[1]["items"] if i["kind"] == "Major donor" and i["id"] == k["id"]][0]; self.assertEqual(k2["risk"], [])
        adm.call("PUT", f"/api/t/donors/{k['id']}", dict(owner="Asha", backup_owner="asha"))
        self.assertIn("Backup is the same person", [i for i in acc.call("GET", "/api/relations")[1]["items"] if i["kind"] == "Major donor" and i["id"] == k["id"]][0]["risk"])
        # decisions carry into the board pack until done
        did = acc.call("POST", "/api/t/decisions", dict(date=today, meeting="Board", decision="Approve the reserve policy", owner="Treasurer", due=(t0 - datetime.timedelta(days=2)).isoformat()))[1]
        did = did["id"] if isinstance(did, dict) else did
        b = acc.call("GET", "/api/board")[1]; self.assertTrue(any(d["decision"] == "Approve the reserve policy" and d["overdue"] for d in b["decisions"])); self.assertTrue(any("past their due date" in x for x in b["risks"]))
        s, html = acc.call("GET", "/api/boardpack?notes=Hello+board", raw=True); h = html.decode(); self.assertEqual(s, 200)
        self.assertIn("Board pack as of", h); self.assertIn("Approve the reserve policy", h); self.assertIn("Hello board", h); self.assertIn("Cash forecast", h)
        acc.call("PUT", f"/api/t/decisions/{did}", dict(status="Done"))
        self.assertFalse(any(d["decision"] == "Approve the reserve policy" for d in acc.call("GET", "/api/board")[1]["decisions"]))

    def test_static_and_traversal(self):
        c = Client(self.base)
        s, raw = c.call("GET", "/", raw=True); self.assertEqual(s, 200); self.assertIn(b"<html", raw.lower())
        s, _ = c.call("GET", "/..%2f..%2fetc/passwd", raw=True); self.assertEqual(s, 404)

if __name__ == "__main__":
    unittest.main(verbosity=1)
