"""Register definitions: fields, list-view SQL (with computed columns), permissions.
The generic CRUD API and the front-end forms/tables are both driven from this file."""

ALL = ["admin", "accountant", "programme", "viewer"]
FIN = ["admin", "accountant"]
PROG = ["admin", "programme"]
BOTH = ["admin", "accountant", "programme"]

def F(k, l, t="text", req=False, **kw):
    d = dict(k=k, l=l, t=t, req=req)
    d.update(kw)
    return d

GENDER = ["Female", "Male", "Other"]
STATUS = ["Active", "Completed", "Dropped"]
FUND_TYPE = ["General", "Restricted", "Corpus"]
YN = ["Y", "N"]

TABLES = {}

def T(name, label, fields, sql, cols, write, **kw):
    TABLES[name] = dict(name=name, label=label, fields=fields, sql=sql, cols=cols, write=write,
                        read=kw.pop("read", ALL), order=kw.pop("order", "t.id DESC"), search=kw.pop("search", []), **kw)

T("donors", "Donors", [
    F("name", "Donor name", req=True), F("phone", "Phone (+91)"), F("city", "City", "list:city"),
    F("donor_type", "Donor type", "list:donor_type"), F("id_no", "ID No (if needed)"),
    F("next_followup", "Next follow-up", "date"), F("email", "Email"), F("birthday", "Birthday (any year, or 2000 if unknown)", "date"),
    F("wishes", "Send greetings and updates by email", "enum:Y,N"), F("msg_optin", "OK to send WhatsApp and SMS (only if they agreed)", "enum:Y,N"), F("language", "Preferred language", "list:language"),
    F("owner", "Relationship owner (who knows this donor)"), F("backup_owner", "Backup person"), F("handover_note", "Handover note (how to look after this donor)", "area"), F("notes", "Notes", "area")],
  """SELECT t.*, COALESCE(g.total,0) total, COALESCE(g.gifts,0) gifts,
     CASE WHEN COALESCE(g.gifts,0)>=:repeat_gifts THEN 'Repeat' WHEN COALESCE(g.gifts,0)=1 THEN 'One gift' ELSE 'New' END level,
     CASE WHEN COALESCE(t.next_followup,'')<>'' AND t.next_followup<=:today THEN 'Due' ELSE '' END follow_up
     FROM donors t LEFT JOIN (SELECT donor_id, SUM(amount) total, COUNT(*) gifts FROM donations GROUP BY donor_id) g ON g.donor_id=t.id""",
  [("code", "ID"), ("name", "Donor"), ("phone", "Phone"), ("city", "City"), ("donor_type", "Type"),
   ("next_followup", "Follow-up", "date"), ("total", "Total given", "money"), ("gifts", "Gifts", "int"),
   ("level", "Level", "badge"), ("follow_up", "Call?", "badge")],
  FIN, prefix="D-", start=101, code="code", search=["code", "name", "phone", "city"], order="t.name")

T("donations", "Donations", [
    F("receipt_no", "Receipt no (auto if blank)"), F("date", "Date", "date", True), F("donor_id", "Donor", "ref:donors", True),
    F("purpose", "Purpose", "list:purpose"), F("fund_type", "Fund type", "enum:" + ",".join(FUND_TYPE)),
    F("mode", "Mode", "list:mode"), F("reference", "Reference"), F("amount", "Amount (₹)", "num", True),
    F("fund_id", "Post to fund (cash book)", "ref:funds"), F("partner_id", "Company or partner (if it came through one)", "ref:partners"),
    F("receipt_given", "Receipt given", "enum:Y,N"), F("thank_you_sent", "Thank-you sent", "enum:Y,N")],
  """SELECT t.*, d.name donor, d.code donor_code, f.name fund FROM donations t
     JOIN donors d ON d.id=t.donor_id LEFT JOIN funds f ON f.id=t.fund_id""",
  [("receipt_no", "Receipt"), ("date", "Date", "date"), ("donor", "Donor"), ("purpose", "Purpose"), ("fund_type", "Fund type"),
   ("mode", "Mode"), ("amount", "Amount", "money"), ("receipt_given", "Receipt", "yn"), ("thank_you_sent", "Thanked", "yn")],
  FIN, prefix="R-", start=2601, code="receipt_no", search=["receipt_no", "d.name", "purpose", "reference"],
  order="t.date DESC, t.id DESC", actions=["receipt"])

T("projects", "Projects", [
    F("name", "Project", req=True), F("place", "Place"), F("lead", "Lead"), F("start", "Start", "date"), F("end", "End", "date"),
    F("target_people", "Target people", "int"), F("budget", "Budget (₹)", "num"), F("stage", "Stage", "list:stage"),
    F("funder", "Funder"), F("fund_type", "Fund type", "enum:" + ",".join(FUND_TYPE)), F("months", "Months", "int"),
    F("funds_promised", "Funds promised (₹)", "num"), F("my_share_pct", "My share % (0-1)", "num"),
    F("purpose", "What it is for (one line)"),
    F("story_person", "Story: person's name", group="Donor story (ask the person before using it)"),
    F("story_before", "Before", "area", group="Donor story (ask the person before using it)"),
    F("story_did", "What we did", "area", group="Donor story (ask the person before using it)"),
    F("story_after", "After", "area", group="Donor story (ask the person before using it)"),
    F("story_quote", "Their own words", "area", group="Donor story (ask the person before using it)"),
    F("story_number", "Story number", group="Donor story (ask the person before using it)"),
    F("story_number_meaning", "What the number means", group="Donor story (ask the person before using it)"),
    F("story_next", "What we will do next", "area", group="Donor story (ask the person before using it)")],
  """SELECT t.*, COALESCE(b.n,0) people_listed,
     CASE WHEN t.target_people>0 THEN ROUND(1.0*COALESCE(b.n,0)/t.target_people,4) END reach,
     COALESCE(a.n,0) activities, COALESCE(a.sp,0) spent,
     CASE WHEN t.budget>0 THEN ROUND(COALESCE(a.sp,0)/t.budget,4) END used,
     CASE WHEN t.stage='Closed' OR COALESCE(t.end,'')='' THEN NULL ELSE CAST(julianday(t.end)-julianday(:today) AS INTEGER) END days_left,
     CASE WHEN t.stage='Closed' OR COALESCE(t.end,'')='' THEN ''
          WHEN t.end<:today THEN 'Past end'
          WHEN julianday(t.end)-julianday(:today)<=:ending_soon_days THEN 'Ending soon' ELSE 'On time' END flag
     FROM projects t
     LEFT JOIN (SELECT project_id, COUNT(*) n FROM beneficiaries GROUP BY project_id) b ON b.project_id=t.id
     LEFT JOIN (SELECT project_id, COUNT(*) n, SUM(spent) sp FROM activities GROUP BY project_id) a ON a.project_id=t.id""",
  [("code", "ID"), ("name", "Project"), ("place", "Place"), ("lead", "Lead"), ("stage", "Stage", "badge"),
   ("end", "End", "date"), ("target_people", "Target", "int"), ("people_listed", "Listed", "int"), ("reach", "Reach", "pct"),
   ("budget", "Budget", "money"), ("spent", "Spent", "money"), ("used", "Used", "pct"), ("flag", "Flag", "badge")],
  PROG, prefix="P-", start=101, code="code", search=["code", "t.name", "place", "lead", "funder"], order="t.name")

T("beneficiaries", "Beneficiaries", [
    F("code", "Person ID (auto if blank)"), F("date_joined", "Date joined", "date"), F("name", "Name", req=True), F("phone", "Phone (+91)"),
    F("village", "Village or ward", "list:village"), F("gender", "Gender", "enum:" + ",".join(GENDER)),
    F("age_group", "Age group", "list:age_group"), F("project_id", "Project", "ref:projects", True),
    F("service", "Service", "list:service"), F("status", "Status", "enum:" + ",".join(STATUS))],
  """SELECT t.*, p.name project FROM beneficiaries t LEFT JOIN projects p ON p.id=t.project_id""",
  [("code", "ID"), ("date_joined", "Joined", "date"), ("name", "Name"), ("village", "Village"), ("gender", "Gender"),
   ("age_group", "Age"), ("project", "Project"), ("service", "Service"), ("status", "Status", "badge")],
  PROG, prefix="B-", start=1001, code="code", search=["t.code", "t.name", "village", "p.name", "service"], order="t.date_joined DESC, t.id DESC")

T("activities", "Activity Log", [
    F("date", "Date", "date", True), F("project_id", "Project", "ref:projects", True), F("activity", "Activity", "list:activity"),
    F("village", "Village or ward", "list:village"), F("people_reached", "People reached", "int"),
    F("volunteers", "Volunteers", "int"), F("spent", "Spent (₹)", "num"), F("note", "Note", "area")],
  """SELECT t.*, p.name project,
     CASE WHEN t.people_reached>0 THEN ROUND(t.spent/t.people_reached,2) END cost_per_person
     FROM activities t JOIN projects p ON p.id=t.project_id""",
  [("date", "Date", "date"), ("project", "Project"), ("activity", "Activity"), ("village", "Village"),
   ("people_reached", "Reached", "int"), ("volunteers", "Volunteers", "int"), ("spent", "Spent", "money"),
   ("cost_per_person", "₹/person", "money")],
  PROG, search=["p.name", "activity", "village", "note"], order="t.date DESC, t.id DESC", actions=["activity_report"])

T("team", "Team (staff & volunteers)", [
    F("code", "Team ID (auto if blank)"), F("name", "Name", req=True), F("role", "Role", "list:role"), F("phone", "Phone (+91)"),
    F("pay_type", "Pay type", "enum:Monthly,Per day,Volunteer", True), F("pay_rate", "Pay rate (₹)", "num"),
    F("active", "Active", "enum:Y,N"), F("email", "Email"), F("birthday", "Birthday (any year, or 2000 if unknown)", "date"),
    F("wishes", "Send greetings and updates by email", "enum:Y,N"), F("bank_account", "Bank account no (for salary sheet)"), F("ifsc", "IFSC")],
  "SELECT t.* FROM team t",
  [("code", "ID"), ("name", "Name"), ("role", "Role"), ("phone", "Phone"), ("pay_type", "Pay type"),
   ("pay_rate", "Rate", "money"), ("active", "Active", "yn")],
  FIN, code="code", search=["code", "name", "role", "phone"], order="t.code")

DAYPAY = """CASE WHEN m.pay_type='Per day' THEN ROUND(CASE t.attendance WHEN 'P' THEN m.pay_rate WHEN 'H' THEN m.pay_rate/2.0 ELSE 0 END
            + t.extra_hours*:extra_hour_rate, 0) ELSE 0 END"""
T("attendance", "Daily Attendance", [
    F("date", "Date", "date", True), F("team_id", "Team member", "ref:team", True),
    F("attendance", "Attendance", "enum:P,A,H,L", True), F("extra_hours", "Extra hours", "num"), F("advance_paid", "Advance paid (₹)", "num")],
  f"""SELECT t.*, m.name member, m.code member_code, m.pay_type, m.pay_rate, {DAYPAY} day_pay
     FROM attendance t JOIN team m ON m.id=t.team_id""",
  [("date", "Date", "date"), ("member_code", "ID"), ("member", "Name"), ("pay_type", "Pay type"), ("attendance", "P/A/H/L", "badge"),
   ("extra_hours", "Extra hrs", "num"), ("advance_paid", "Advance", "money"), ("day_pay", "Day's pay", "money")],
  BOTH, search=["m.name", "m.code"], order="t.date DESC, m.code", hint="P present · A absent · H half day · L leave")

T("volunteer_log", "Volunteer Log", [
    F("date", "Date", "date", True), F("team_id", "Volunteer", "ref:team", True), F("duty", "Duty", "list:duty"),
    F("hours", "Hours", "num"), F("km", "Travel km", "num"), F("other_paid", "Food or other paid (₹)", "num")],
  """SELECT t.*, m.name member, m.code member_code, ROUND(t.km*:travel_per_km,0)+t.other_paid paid_back
     FROM volunteer_log t JOIN team m ON m.id=t.team_id""",
  [("date", "Date", "date"), ("member_code", "ID"), ("member", "Name"), ("duty", "Duty"), ("hours", "Hours", "num"),
   ("km", "Km", "num"), ("other_paid", "Food/other", "money"), ("paid_back", "Paid back", "money")],
  BOTH, search=["m.name", "m.code", "duty"], order="t.date DESC, t.id DESC")

T("grants", "Grants", [
    F("code", "Grant ID (auto if blank)"), F("funder", "Funder", req=True), F("project_id", "Project", "ref:projects"),
    F("start", "Start", "date"), F("end", "End", "date"), F("sanctioned", "Sanctioned (₹)", "num", True),
    F("report_due", "Report due", "date"), F("owner", "Relationship owner"), F("backup_owner", "Backup person"), F("notes", "Notes", "area")],
  """SELECT t.*, p.name project, COALESCE(i.s,0) received, COALESCE(g.s,0) spent, COALESCE(i.s,0)-COALESCE(g.s,0) in_hand,
     CASE WHEN t.sanctioned>0 THEN ROUND(COALESCE(g.s,0)/t.sanctioned,4) END used,
     CASE WHEN COALESCE(t.start,'')<>'' AND COALESCE(t.end,'')<>'' AND t.end>t.start THEN
        MAX(0,MIN(1,(julianday(:today)-julianday(t.start))/(julianday(t.end)-julianday(t.start)))) END time_gone,
     CASE WHEN COALESCE(t.report_due,'')='' THEN NULL ELSE CAST(julianday(t.report_due)-julianday(:today) AS INTEGER) END report_in_days
     FROM grants t LEFT JOIN projects p ON p.id=t.project_id
     LEFT JOIN (SELECT grant_id, SUM(amount) s FROM instalments GROUP BY grant_id) i ON i.grant_id=t.id
     LEFT JOIN (SELECT grant_id, SUM(amount) s FROM grant_spend GROUP BY grant_id) g ON g.grant_id=t.id""",
  [("code", "ID"), ("funder", "Funder"), ("project", "Project"), ("end", "End", "date"), ("sanctioned", "Sanctioned", "money"),
   ("received", "Received", "money"), ("spent", "Spent", "money"), ("in_hand", "In hand", "money"), ("used", "Used", "pct"),
   ("time_gone", "Time", "pct"), ("pace", "Pace", "badge"), ("report_in_days", "Report in", "days")],
  FIN, prefix="G-", start=1, pad=2, code="code", search=["t.code", "funder", "p.name"], order="t.code", actions=["utilisation"])

T("instalments", "Grant Instalments", [
    F("date", "Date", "date", True), F("grant_id", "Grant", "ref:grants", True), F("reference", "Reference"),
    F("amount", "Amount (₹)", "num", True), F("fund_id", "Post to fund (cash book)", "ref:funds"), F("note", "Note")],
  """SELECT t.*, g.code grant_code, g.funder, f.name fund FROM instalments t JOIN grants g ON g.id=t.grant_id LEFT JOIN funds f ON f.id=t.fund_id""",
  [("date", "Date", "date"), ("grant_code", "Grant"), ("funder", "Funder"), ("reference", "Reference"), ("amount", "Amount", "money"), ("note", "Note")],
  FIN, search=["g.code", "g.funder", "reference"], order="t.date DESC, t.id DESC")

T("grant_spend", "Grant Spend", [
    F("date", "Date", "date", True), F("grant_id", "Grant", "ref:grants", True), F("head", "Head", "list:spend_head"),
    F("voucher_no", "Voucher no"), F("paid_to", "Paid to"), F("amount", "Amount (₹)", "num", True),
    F("bill_kept", "Bill kept", "enum:Y,N"), F("fund_id", "Post to fund (cash book)", "ref:funds")],
  """SELECT t.*, g.code grant_code, g.funder, f.name fund FROM grant_spend t JOIN grants g ON g.id=t.grant_id LEFT JOIN funds f ON f.id=t.fund_id""",
  [("date", "Date", "date"), ("grant_code", "Grant"), ("head", "Head"), ("voucher_no", "Voucher"), ("paid_to", "Paid to"),
   ("amount", "Amount", "money"), ("bill_kept", "Bill", "yn")],
  FIN, search=["g.code", "head", "voucher_no", "paid_to"], order="t.date DESC, t.id DESC")

T("funds", "Funds", [
    F("name", "Fund", req=True), F("type", "Type", "enum:" + ",".join(FUND_TYPE), True), F("purpose", "Purpose"), F("opening", "Opening (₹)", "num")],
  """SELECT t.*, COALESCE(r.s,0) received, COALESCE(p.s,0) spent, t.opening+COALESCE(r.s,0)-COALESCE(p.s,0) balance,
     COALESCE(r.s,0)-COALESCE(p.s,0) surplus,
     CASE WHEN t.opening+COALESCE(r.s,0)-COALESCE(p.s,0)<0 THEN 'Below zero' ELSE 'OK' END status
     FROM funds t
     LEFT JOIN (SELECT fund_id, SUM(amount) s FROM cash_book WHERE type='Receipt' GROUP BY fund_id) r ON r.fund_id=t.id
     LEFT JOIN (SELECT fund_id, SUM(amount) s FROM cash_book WHERE type='Payment' GROUP BY fund_id) p ON p.fund_id=t.id""",
  [("name", "Fund"), ("type", "Type", "badge"), ("purpose", "Purpose"), ("opening", "Opening", "money"), ("received", "Received", "money"),
   ("spent", "Spent", "money"), ("balance", "Balance", "money"), ("status", "Status", "badge")],
  FIN, search=["t.name", "purpose"], order="t.name")

T("cash_book", "Cash Book", [
    F("date", "Date", "date", True), F("voucher_no", "Voucher no (auto if blank)"), F("type", "Type", "enum:Receipt,Payment", True),
    F("fund_id", "Fund", "ref:funds", True), F("head", "Head"), F("party", "Party"), F("mode", "Mode", "list:mode"),
    F("amount", "Amount (₹)", "num", True), F("note", "Note")],
  "SELECT t.*, f.name fund FROM cash_book t JOIN funds f ON f.id=t.fund_id",
  [("date", "Date", "date"), ("voucher_no", "Voucher"), ("type", "Type", "badge"), ("fund", "Fund"), ("head", "Head"), ("party", "Party"),
   ("mode", "Mode"), ("amount", "Amount", "money"), ("source", "Posted from")],
  FIN, search=["voucher_no", "f.name", "head", "party", "note"], order="t.date DESC, t.id DESC", actions=["voucher"])

T("budget_lines", "Budget Lines", [
    F("project_id", "Project", "ref:projects", True), F("line", "Line", req=True), F("grp", "Group", "list:budget_group"),
    F("qty", "Qty", "num"), F("unit_cost", "Unit cost (₹)", "num"), F("times", "Times", "num")],
  "SELECT t.*, p.name project, ROUND(t.qty*t.unit_cost*t.times,2) amount FROM budget_lines t JOIN projects p ON p.id=t.project_id",
  [("project", "Project"), ("line", "Line"), ("grp", "Group"), ("qty", "Qty", "num"), ("unit_cost", "Unit cost", "money"),
   ("times", "Times", "num"), ("amount", "Amount", "money")],
  BOTH, search=["p.name", "line", "grp"], order="p.name, t.id")

T("appeals", "Fundraising Appeals", [F("name", "Appeal or activity", req=True), F("cost", "What it cost (₹)", "num"), F("raised", "What it raised (₹)", "num")],
  """SELECT t.*, t.raised-t.cost net_raised, CASE WHEN t.raised>0 THEN ROUND(100.0*t.cost/t.raised,2) END cost_per_100 FROM appeals t""",
  [("name", "Appeal"), ("cost", "Cost", "money"), ("raised", "Raised", "money"), ("net_raised", "Net raised", "money"), ("cost_per_100", "Cost per ₹100", "money")],
  FIN, search=["name"], order="t.name")

T("cashflow_plan", "Cash Flow Plan", [F("month", "Month (YYYY-MM)", req=True), F("expected_in", "Money expected in (₹)", "num"), F("expected_out", "Money going out (₹)", "num")],
  "SELECT t.* FROM cashflow_plan t",
  [("month", "Month"), ("expected_in", "In", "money"), ("expected_out", "Out", "money")], FIN, order="t.month")

T("records", "Document Records", [
    F("record_no", "Record no (auto if blank)"), F("date", "Date", "date", True), F("party", "Donor or party"), F("phone", "Phone (+91)"),
    F("address", "Address"), F("project", "Project"), F("purpose", "Fund or purpose"), F("period_ref", "Period or ref"),
    F("people", "People", "int"), F("amount", "Amount (₹)", "num"), F("received", "Received (₹)", "num"), F("next_date", "Next date", "date")],
  "SELECT t.*, MAX(0,t.amount-t.received) balance FROM records t",
  [("record_no", "Record"), ("date", "Date", "date"), ("party", "Party"), ("project", "Project"), ("purpose", "Purpose"),
   ("amount", "Amount", "money"), ("received", "Received", "money"), ("balance", "Balance", "money")],
  BOTH, prefix="DOC-", start=401, code="record_no", search=["record_no", "party", "project", "purpose"], order="t.date DESC, t.id DESC", actions=["print_record"])

T("record_lines", "Record Lines", [
    F("record_id", "Record", "ref:records", True), F("item", "Item"), F("detail", "Detail"), F("qty", "Qty", "num"), F("unit", "Unit", "list:unit"),
    F("times", "Times", "num"), F("rate", "Rate (₹)", "num")],
  "SELECT t.*, r.record_no, ROUND(t.qty*t.times*t.rate,2) amount FROM record_lines t JOIN records r ON r.id=t.record_id",
  [("record_no", "Record"), ("item", "Item"), ("detail", "Detail"), ("qty", "Qty", "num"), ("unit", "Unit"), ("times", "Times", "num"),
   ("rate", "Rate", "money"), ("amount", "Amount", "money")],
  BOTH, search=["r.record_no", "item", "detail"], order="r.record_no, t.id")

T("results", "Project Results", [
    F("project_id", "Project", "ref:projects", True), F("result", "Result", req=True), F("unit", "Unit", "list:result_unit"),
    F("target", "Target", "num"), F("achieved", "Achieved so far", "num"), F("people_group", "People group (only if it counts people)", "list:people_group")],
  """SELECT t.*, p.name project, CASE WHEN t.target>0 THEN ROUND(t.achieved/t.target,4) END done FROM results t JOIN projects p ON p.id=t.project_id""",
  [("project", "Project"), ("result", "Result"), ("unit", "Unit"), ("target", "Target", "num"), ("achieved", "Achieved", "num"),
   ("people_group", "People group"), ("done", "Done", "pct")],
  PROG, search=["p.name", "result"], order="p.name, t.id")

T("project_spend", "Project Money (donor report)", [
    F("project_id", "Project", "ref:projects", True), F("head", "Spending head", "list:spend_head", True), F("budget", "Budget (₹)", "num"),
    F("used", "Used so far (₹)", "num"), F("note", "Note")],
  """SELECT t.*, p.name project, t.budget-t.used balance, CASE WHEN t.budget>0 THEN ROUND(t.used/t.budget,4) END used_pct
     FROM project_spend t JOIN projects p ON p.id=t.project_id""",
  [("project", "Project"), ("head", "Spending head"), ("budget", "Budget", "money"), ("used", "Used", "money"),
   ("balance", "Balance", "money"), ("used_pct", "Used", "pct"), ("note", "Note")],
  BOTH, search=["p.name", "head"], order="p.name, t.id")

T("compliance", "Compliance calendar", [
    F("title", "What is due (e.g. Audit report, TDS return)", req=True), F("due_date", "Due date (leave blank until your CA confirms)", "date"),
    F("repeat", "Repeats", "enum:None,Monthly,Quarterly,Yearly"), F("remind_days", "Remind me this many days before", "int"),
    F("last_done", "Last done on", "date"), F("notes", "Notes (your own; check dates with your CA)", "area")],
  "SELECT t.* FROM compliance t",
  [("title", "What"), ("repeat", "Repeats"), ("next_due", "Next due", "date"), ("days_left", "Days left", "days"), ("cstatus", "Status", "badge"), ("last_done", "Last done", "date")],
  FIN, search=["title", "notes"], order="t.due_date", actions=["mark_done"],
  hint="Dates are your own entries. This calendar reminds you; it does not give tax or legal advice.")

T("pledges", "Pledges from the Donate page", [
    F("name", "Name", req=True), F("phone", "Phone"), F("email", "Email"), F("amount", "Amount (₹)", "num"), F("message", "Message", "area"),
    F("status", "Status", "enum:New,Converted,Dismissed")],
  "SELECT t.* FROM pledges t",
  [("ts", "When"), ("name", "Name"), ("phone", "Phone"), ("email", "Email"), ("amount", "Amount", "money"), ("message", "Message"), ("status", "Status", "badge")],
  FIN, read=FIN, search=["name", "phone", "email", "message"], order="t.id DESC", actions=["convert"],
  hint="People who filled the public Donate page. Check your bank/UPI for the money, then convert them to donors and record the donation.")

T("contacts", "Contacts (non-donors)", [
    F("code", "ID (auto if blank)"), F("name", "Name", req=True), F("phone", "Phone (+91)"), F("email", "Email"), F("organisation", "Organisation"),
    F("relation", "Who are they", "list:relation"), F("city", "City", "list:city"), F("tags", "Groups (comma separated, e.g. Volunteers, Media)"),
    F("msg_optin", "OK to send WhatsApp and SMS (only if they agreed)", "enum:Y,N"), F("wishes", "OK to send emails", "enum:Y,N"), F("language", "Preferred language", "list:language"), F("notes", "Notes", "area")],
  "SELECT t.* FROM contacts t",
  [("code", "ID"), ("name", "Name"), ("phone", "Phone"), ("email", "Email"), ("relation", "Who"), ("tags", "Groups"), ("msg_optin", "Msgs OK", "yn")],
  FIN, prefix="C-", start=1001, code="code", search=["t.code", "t.name", "phone", "email", "organisation", "tags"], order="t.name",
  hint="Volunteers, trustees, officials, media, well-wishers: anyone who is not a donor. Use Import CSV to add many at once, then message them by group.")

T("interactions", "Contact log (calls, visits, messages)", [
    F("date", "Date", "date", True), F("donor_id", "Donor", "ref:donors", True),
    F("channel", "How", "enum:Call,WhatsApp,Email,SMS,Visit,Meeting,Event,Other"), F("direction", "Who started", "enum:Out,In"),
    F("summary", "What was said or done", "area", True),
    F("outcome", "Outcome", "enum:Reached,No answer,Promised gift,Gift received,Declined,Needs follow-up,Done"),
    F("next_followup", "Follow up on (updates the donor's next follow-up)", "date"), F("owner", "Handled by")],
  "SELECT t.*, d.name donor, d.code donor_code FROM interactions t JOIN donors d ON d.id=t.donor_id",
  [("date", "Date", "date"), ("donor", "Donor"), ("channel", "How"), ("outcome", "Outcome", "badge"), ("summary", "Summary"), ("next_followup", "Next follow-up", "date"), ("owner", "By")],
  FIN, search=["d.name", "summary", "owner"], order="t.date DESC, t.id DESC",
  hint="Log every call, visit and message here. Setting a follow-up date puts the donor on the Follow-ups board and in the morning digest.")

T("templates", "Message templates", [
    F("name", "Template name", req=True), F("channel", "For", "enum:Email,WhatsApp,SMS", True), F("subject", "Email subject"),
    F("body", "Message ({name} {first_name} {org} {contact} {upi})", "area", True),
    F("provider_template", "Approved template name (WhatsApp) or DLT template ID (SMS)"),
    F("variables", "Merge fields in order, e.g. first_name,org (fills {{1}}, {{2}} or VAR1, VAR2)")],
  "SELECT t.* FROM templates t",
  [("name", "Name"), ("channel", "For"), ("subject", "Subject"), ("body", "Message")],
  FIN, search=["name", "subject", "body"], order="t.name",
  hint="Reusable messages for the Send messages page. Edit the wording to suit your organisation.")

T("journey", "Beneficiary journey (steps)", [
    F("beneficiary_id", "Person", "ref:beneficiaries", True), F("date", "Date", "date", True), F("stage", "Step", "list:journey_stage", True),
    F("detail", "What happened", "area"), F("outcome", "Result or outcome (e.g. passed Class 10, got a job, weight 14 kg)"), F("recorded_by", "Recorded by")],
  """SELECT t.*, b.name person, b.code person_code, p.name project FROM journey t JOIN beneficiaries b ON b.id=t.beneficiary_id LEFT JOIN projects p ON p.id=b.project_id""",
  [("date", "Date", "date"), ("person", "Person"), ("project", "Project"), ("stage", "Step", "badge"), ("detail", "What happened"), ("outcome", "Outcome"), ("recorded_by", "By")],
  PROG, search=["b.name", "b.code", "stage", "detail", "outcome", "p.name"], order="t.date DESC, t.id DESC",
  hint="One line for each step in a person's journey: enrolled, assessed, service given, follow-up, outcome. Open a person under Journey to see their whole timeline.")

T("commitments", "Regular giving promises (monthly / yearly)", [
    F("donor_id", "Donor", "ref:donors", True), F("amount", "Amount each time (₹)", "num", True),
    F("frequency", "How often", "enum:Monthly,Quarterly,Half-yearly,Yearly", True), F("start", "First due date", "date", True), F("end", "Ends on (blank = no end)", "date"),
    F("purpose", "Purpose"), F("status", "Status", "enum:Active,Paused,Ended"), F("notes", "Notes", "area")],
  """SELECT t.*, d.name donor, d.code donor_code FROM commitments t JOIN donors d ON d.id=t.donor_id""",
  [("donor", "Donor"), ("amount", "Amount", "money"), ("frequency", "How often"), ("start", "First due", "date"), ("end", "Ends", "date"), ("purpose", "Purpose"), ("status", "Status", "badge")],
  FIN, search=["d.name", "d.code", "purpose", "notes"], order="d.name",
  hint="A donor who promised to give every month, quarter or year. The Giving promises board shows who has paid, who is due and who is late, by matching the donations you record.")

T("partners", "Corporate partners", [
    F("code", "ID (auto if blank)"), F("name", "Company", req=True), F("sector", "Sector", "list:partner_sector"), F("stage", "Stage", "list:partner_stage", True),
    F("csr_focus", "CSR focus areas of the company"), F("expected_amount", "Expected support this year (₹)", "num"), F("renewal_date", "Renewal or decision date", "date"),
    F("contact_name", "Contact person"), F("contact_phone", "Contact phone"), F("contact_email", "Contact email"),
    F("last_contact", "Last contact", "date"), F("next_step", "Next step"), F("next_step_date", "Next step date", "date"),
    F("owner", "Relationship owner"), F("backup_owner", "Backup person"), F("handover_note", "Handover note", "area"), F("notes", "Notes", "area")],
  """SELECT t.*, COALESCE(d.s,0) given, COALESCE(d.n,0) gifts, COALESCE(e.n,0) events, COALESCE(e.h,0) hours,
     CASE WHEN COALESCE(t.renewal_date,'')='' THEN NULL ELSE CAST(julianday(t.renewal_date)-julianday(:today) AS INTEGER) END renew_in_days
     FROM partners t LEFT JOIN (SELECT partner_id, SUM(amount) s, COUNT(*) n FROM donations WHERE partner_id IS NOT NULL GROUP BY partner_id) d ON d.partner_id=t.id
     LEFT JOIN (SELECT partner_id, COUNT(*) n, SUM(hours) h FROM partner_events WHERE status='Done' GROUP BY partner_id) e ON e.partner_id=t.id""",
  [("code", "ID"), ("name", "Company"), ("stage", "Stage", "badge"), ("expected_amount", "Expected", "money"), ("given", "Given so far", "money"), ("events", "Events", "int"),
   ("renewal_date", "Renewal", "date"), ("next_step", "Next step"), ("owner", "Owner")],
  FIN, prefix="P-", start=1, pad=2, code="code", search=["t.code", "t.name", "csr_focus", "contact_name", "owner"], order="t.name",
  hint="Every company you work with or hope to. Move it along the stages as talks progress. Record gifts that came through a company by choosing it on the donation.")

T("partner_events", "Office and volunteering events", [
    F("date", "Date", "date", True), F("title", "Event", req=True), F("partner_id", "Company", "ref:partners"), F("kind", "Kind of event", "list:event_kind"),
    F("project_id", "Project it supports", "ref:projects"), F("venue", "Venue"), F("status", "Status", "enum:Planned,Done,Cancelled"),
    F("planned_people", "Employees expected", "int"), F("attended", "Employees who came", "int"), F("hours", "Total volunteer hours", "num"),
    F("raised", "Money raised at the event (₹)", "num"), F("note", "What happened", "area")],
  """SELECT t.*, pa.name partner, p.name project FROM partner_events t LEFT JOIN partners pa ON pa.id=t.partner_id LEFT JOIN projects p ON p.id=t.project_id""",
  [("date", "Date", "date"), ("title", "Event"), ("partner", "Company"), ("kind", "Kind"), ("status", "Status", "badge"), ("attended", "Came", "int"), ("hours", "Hours", "num"), ("raised", "Raised", "money")],
  BOTH, search=["t.title", "pa.name", "t.kind", "t.venue"], order="t.date DESC, t.id DESC", actions=["eventnote"],
  hint="A volunteering day, talk, drive or visit with a company. After it is done, fill in who came and the hours, then use Thank-you note to get a ready note for the company.")

T("tranches", "Expected funder payments", [
    F("grant_id", "Grant", "ref:grants", True), F("due_date", "Payment due on", "date", True), F("amount", "Amount (₹)", "num", True),
    F("received_date", "Date received (fill in when it arrives)", "date"), F("note", "Note")],
  """SELECT t.*, g.code grant_code, g.funder,
     CASE WHEN COALESCE(t.received_date,'')<>'' THEN 'Received' WHEN t.due_date<:today THEN 'Overdue' ELSE 'Expected' END state,
     CASE WHEN COALESCE(t.received_date,'')='' AND t.due_date<:today THEN CAST(julianday(:today)-julianday(t.due_date) AS INTEGER) END days_late
     FROM tranches t JOIN grants g ON g.id=t.grant_id""",
  [("grant_code", "Grant"), ("funder", "Funder"), ("due_date", "Due", "date"), ("amount", "Amount", "money"), ("state", "State", "badge"), ("days_late", "Days late", "int"), ("received_date", "Received", "date")],
  FIN, search=["g.code", "g.funder", "note"], order="t.due_date",
  hint="Money a funder has promised to send on a date. When it arrives, fill in the date received and record the money under Grant Instalments as usual. Overdue payments show in the cash forecast.")

T("decisions", "Board decisions and actions", [
    F("date", "Meeting date", "date", True), F("meeting", "Meeting (e.g. Board, Finance committee)"), F("decision", "Decision or action", "area", True),
    F("owner", "Who will do it"), F("due", "Due by", "date"), F("status", "Status", "enum:Open,Done,Dropped"), F("notes", "Notes", "area")],
  "SELECT t.*, CASE WHEN t.status='Open' AND COALESCE(t.due,'')<>'' AND t.due<:today THEN 'Overdue' ELSE t.status END state FROM decisions t",
  [("date", "Date", "date"), ("meeting", "Meeting"), ("decision", "Decision"), ("owner", "Owner"), ("due", "Due", "date"), ("state", "Status", "badge")],
  FIN, search=["decision", "owner", "meeting"], order="t.date DESC, t.id DESC",
  hint="Every decision from a board or committee meeting. Open items carry forward into the board pack until marked Done.")

T("outcomes", "Sponsor an outcome (what a gift buys)", [
    F("title", "What the gift does (e.g. Keeps one girl in school for a year)", req=True), F("unit_cost", "Cost of one (\u20b9)", "num", True),
    F("per", "Per", "enum:year,month,one-time"), F("project_id", "Project", "ref:projects"), F("description", "A line about it", "area"), F("active", "Show on the donate page", "enum:Y,N")],
  """SELECT t.*, p.name project FROM outcomes t LEFT JOIN projects p ON p.id=t.project_id""",
  [("title", "Outcome"), ("unit_cost", "Cost of one", "money"), ("per", "Per"), ("project", "Project"), ("active", "On donate page")],
  FIN, search=["t.title", "p.name"], order="t.unit_cost",
  hint="Concrete things a gift can buy, with a price. They appear on your public Donate page so donors can pick one. Set the price from your own project costs.")

T("legacies", "Legacy and bequest pipeline", [
    F("donor_id", "Donor (if already on your list)", "ref:donors"), F("name", "Name (if not a donor yet)"), F("stage", "Stage", "list:legacy_stage", True),
    F("expected", "Expected amount (\u20b9, a guess is fine)", "num"), F("last_contact", "Last contact", "date"), F("next_contact", "Next contact", "date"),
    F("owner", "Who looks after this"), F("notes", "Notes (private)", "area")],
  """SELECT t.*, COALESCE(d.name, t.name) person FROM legacies t LEFT JOIN donors d ON d.id=t.donor_id""",
  [("person", "Person"), ("stage", "Stage", "badge"), ("expected", "Expected", "money"), ("last_contact", "Last contact", "date"), ("next_contact", "Next contact", "date"), ("owner", "Owner")],
  FIN, read=FIN, search=["t.name", "d.name", "t.owner", "t.notes"], order="t.next_contact",
  hint="People who may remember the trust in a will. Keep the relationship warm and private. Never share this list.")

T("risks", "Risk register", [
    F("title", "Risk (what could go wrong)", req=True), F("category", "Kind of risk", "list:risk_category"), F("likelihood", "How likely (1 = rare, 5 = almost sure)", "enum:1,2,3,4,5"),
    F("impact", "How bad (1 = small, 5 = severe)", "enum:1,2,3,4,5"), F("owner", "Who watches it"), F("mitigation", "What we do about it", "area"),
    F("status", "Status", "enum:Open,Watching,Closed"), F("review_date", "Review on", "date"), F("notes", "Notes", "area")],
  """SELECT t.*, (t.likelihood*t.impact) score,
     CASE WHEN t.likelihood*t.impact>=15 THEN 'High' WHEN t.likelihood*t.impact>=8 THEN 'Medium' ELSE 'Low' END level,
     CASE WHEN t.status<>'Closed' AND COALESCE(t.review_date,'')<>'' AND t.review_date<:today THEN 'Review overdue' ELSE t.status END state FROM risks t""",
  [("title", "Risk"), ("category", "Kind"), ("score", "Score", "int"), ("level", "Level", "badge"), ("owner", "Owner"), ("review_date", "Review", "date"), ("state", "Status", "badge")],
  FIN, read=FIN, search=["t.title", "category", "owner", "mitigation"], order="score DESC, t.title",
  hint="A short list of the things that could hurt the trust, who watches each one, and what you do about it. Review it at every board meeting. Funders and auditors often ask to see it.")

T("incidents", "Incident and complaint register", [
    F("date", "Date", "date", True), F("kind", "Kind", "list:incident_kind", True), F("project_id", "Project", "ref:projects"), F("people", "Who was involved (use initials if sensitive)"),
    F("description", "What happened", "area", True), F("action_taken", "What was done", "area"), F("reported_to", "Reported to (trustee, police, funder, none)"),
    F("owner", "Who is handling it"), F("status", "Status", "enum:Open,Closed"), F("closed_on", "Closed on", "date")],
  """SELECT t.*, p.name project,
     CASE WHEN t.status='Open' THEN CAST(julianday(:today)-julianday(t.date) AS INTEGER) END open_days FROM incidents t LEFT JOIN projects p ON p.id=t.project_id""",
  [("date", "Date", "date"), ("kind", "Kind", "badge"), ("project", "Project"), ("description", "What happened"), ("owner", "Handling"), ("status", "Status", "badge"), ("open_days", "Days open", "int")],
  ["admin"], read=["admin"], search=["t.kind", "t.description", "t.people", "t.owner", "p.name"], order="t.date DESC, t.id DESC",
  hint="Safeguarding concerns, accidents, complaints, loss or fraud. Only administrators can see this page. Write facts, not opinions, and close each one when it is resolved.")

T("event_people", "People who came to an event", [
    F("event_id", "Event", "ref:partner_events", True), F("name", "Name", req=True), F("hours", "Hours given", "num"), F("role", "What they did"), F("note", "Note")],
  """SELECT t.*, e.title event, e.date event_date FROM event_people t JOIN partner_events e ON e.id=t.event_id""",
  [("event_date", "Event date", "date"), ("event", "Event"), ("name", "Name"), ("hours", "Hours", "num"), ("role", "Role")],
  BOTH, read=BOTH, search=["t.name", "e.title", "t.role"], order="e.date DESC, t.name",
  hint="Add each person who came to an office event. The number who came and the hours are then added up for you in the event and the company page.")

def meta():
    out = {}
    for n, t in TABLES.items():
        out[n] = dict(name=n, label=t["label"], fields=t["fields"], cols=[list(c) if len(c) == 3 else [c[0], c[1], "text"] for c in t["cols"]],
                      write=t["write"], read=t["read"], actions=t.get("actions", []), hint=t.get("hint", ""))
    return out

T("policies", "Policy register", [
    F("name", "Policy (e.g. Safeguarding and child protection)", req=True), F("kind", "Kind", "list:policy_kind"), F("adopted_on", "Adopted by the board on", "date"),
    F("next_review", "Review again on", "date"), F("owner", "Who looks after it"), F("staff_signed", "Staff have signed they read it", "enum:No,Partly,Yes"),
    F("link", "Where the signed copy is kept (drive link or file name)"), F("notes", "Notes", "area")],
  """SELECT t.*, CASE WHEN COALESCE(t.adopted_on,'')='' THEN 'Not adopted yet' WHEN COALESCE(t.next_review,'')<>'' AND t.next_review<:today THEN 'Review overdue' ELSE 'In place' END state FROM policies t""",
  [("name", "Policy"), ("kind", "Kind"), ("adopted_on", "Adopted", "date"), ("next_review", "Review", "date"), ("staff_signed", "Staff signed"), ("owner", "Owner"), ("state", "State", "badge")],
  BOTH, read=FIN, search=["t.name", "kind", "owner", "notes"], order="t.name",
  hint="The written rules the trust works by. Funders and auditors ask to see them, and they protect trustees. Keep the signed copy in your drive and note the link here.")

T("trustees", "Trustees and members", [
    F("name", "Name", req=True), F("role", "Role", "list:trustee_role"), F("since", "Since", "date"), F("term_end", "Term ends (if any)", "date"),
    F("phone", "Phone"), F("email", "Email"), F("id_no", "PAN or ID no"), F("status", "Status", "enum:Active,Retired"), F("notes", "Notes", "area")],
  "SELECT t.* FROM trustees t",
  [("name", "Name"), ("role", "Role"), ("since", "Since", "date"), ("term_end", "Term ends", "date"), ("phone", "Phone"), ("status", "Status", "badge")],
  FIN, read=FIN, search=["t.name", "role", "phone", "email"], order="t.status, t.name",
  hint="Who the trustees and members are, from when. Your registrar, bank and auditor may ask for this list. Keep it current when someone joins or leaves.")

T("meetings", "Meetings and minutes", [
    F("date", "Date", "date", True), F("kind", "Kind of meeting", "list:meeting_kind", True), F("place", "Place"), F("attendees", "Who attended", "area"),
    F("quorum", "Quorum met", "enum:Y,N"), F("agenda", "Agenda", "area"), F("minutes", "Minutes (short)", "area"),
    F("minutes_link", "Signed minutes (drive link or file name)"), F("next_date", "Next meeting on", "date")],
  "SELECT t.* FROM meetings t",
  [("date", "Date", "date"), ("kind", "Kind"), ("place", "Place"), ("quorum", "Quorum", "yn"), ("minutes_link", "Signed minutes"), ("next_date", "Next", "date")],
  FIN, read=FIN, search=["kind", "place", "attendees", "agenda", "minutes"], order="t.date DESC",
  hint="A record of each board meeting, the AGM and the POSH committee meeting. Auditors and funders ask for minutes. Record what was decided in Board decisions too, so the actions get followed up.")

T("social_posts", "Social media posts", [
    F("title", "What the post is about", req=True), F("platform", "Where it will go", "list:social_platform"), F("plan_date", "Planned date", "date"),
    F("project_id", "Project", "ref:projects"), F("media_id", "Photo or video (only those with consent)", "ref:media"),
    F("language", "Language", "enum:English,Hindi,Marathi,Other"), F("caption", "Caption", "area"),
    F("status", "Status", "enum:Idea,Drafted,Approved,Posted"), F("owner", "Written by"), F("approved_by", "Approved by (must be a different person)"),
    F("names_ok", "Anyone named in it has agreed", "enum:N,Y"), F("posted_on", "Posted on", "date"), F("post_link", "Link to the post"),
    F("reach", "People reached", "int"), F("reactions", "Likes, shares, comments", "int"), F("gifts_amount", "Gifts that came from it (\u20b9)", "num"), F("notes", "Notes", "area")],
  """SELECT t.*, p.name project,
     CASE WHEN t.status IN ('Idea','Drafted','Approved') AND COALESCE(t.plan_date,'')<>'' AND t.plan_date<:today THEN 'Late' ELSE t.status END state
     FROM social_posts t LEFT JOIN projects p ON p.id=t.project_id""",
  [("plan_date", "Planned", "date"), ("title", "Post"), ("platform", "Where"), ("project", "Project"), ("language", "Language"), ("state", "Status", "badge"), ("reach", "Reached", "int"), ("gifts_amount", "Gifts", "money")],
  BOTH, search=["t.title", "t.caption", "platform", "p.name"], order="t.plan_date DESC, t.id DESC",
  hint="Plan and approve posts here, then publish them with Meta Business Suite, Buffer or the app itself. Only photos with consent can be used, and a second person must approve. Use Post ideas to start from your real work.")

T("plan_calendar", "Festival and giving calendar", [
    F("date", "Date", "date", True), F("title", "Occasion", req=True), F("kind", "Kind", "list:plan_kind"), F("idea", "Campaign idea", "area"),
    F("project_id", "Project to raise for", "ref:projects"), F("status", "Status", "enum:Idea,Planned,Running,Done,Skipped"), F("owner", "Who looks after it"),
    F("goal", "Goal (\u20b9)", "num"), F("raised", "Raised (\u20b9)", "num"), F("notes", "Notes (confirm festival dates on a panchang)", "area")],
  """SELECT t.*, p.name project,
     CASE WHEN t.status IN ('Done','Skipped') THEN t.status
          WHEN t.date<:today THEN 'Passed'
          WHEN julianday(t.date)-julianday(:today)<=28 AND t.status IN ('Idea','Planned') THEN 'Prepare now'
          ELSE t.status END state FROM plan_calendar t LEFT JOIN projects p ON p.id=t.project_id""",
  [("date", "Date", "date"), ("title", "Occasion"), ("kind", "Kind"), ("project", "Project"), ("goal", "Goal", "money"), ("raised", "Raised", "money"), ("state", "Status", "badge")],
  FIN, read=BOTH, search=["t.title", "idea", "kind", "owner"], order="t.date",
  hint="Festivals, awareness days and giving windows with a campaign plan for each. Start preparing four weeks before. Use 'Add the standard calendar' once, then edit the dates and ideas for your own donors.")

T("csr_pipeline", "Company funding pipeline", [
    F("company", "Company", req=True), F("kind", "Kind of support", "list:pipeline_kind"),
    F("stage", "Stage", "enum:Target,Approached,Pitched,Due diligence,Plan approval,Sanctioned,Disbursing,Reporting,Renewal,Declined"),
    F("contact", "Contact person and phone or email"), F("focus", "Their focus area (e.g. education, health)"), F("project_id", "Our project", "ref:projects"),
    F("ask", "What we asked for (\u20b9)", "num"), F("sanctioned", "Sanctioned (\u20b9)", "num"), F("decision_by", "Decision expected by", "date"),
    F("next_step", "Next step"), F("next_date", "Next step on", "date"), F("owner", "Who looks after it"), F("notes", "Notes", "area")],
  """SELECT t.*, p.name project,
     CASE WHEN t.stage IN ('Declined') THEN 'Closed'
          WHEN COALESCE(t.next_date,'')<>'' AND t.next_date<:today AND t.stage<>'Disbursing' THEN 'Step overdue' ELSE t.stage END state
     FROM csr_pipeline t LEFT JOIN projects p ON p.id=t.project_id""",
  [("company", "Company"), ("kind", "Kind"), ("stage", "Stage"), ("ask", "Asked", "money"), ("sanctioned", "Sanctioned", "money"), ("next_step", "Next step"), ("next_date", "On", "date"), ("state", "State", "badge")],
  FIN, read=FIN, search=["t.company", "contact", "focus", "next_step", "owner"], order="t.next_date, t.company",
  hint="Every company you are talking to about CSR, employee giving, matching gifts or volunteering, and where each one stands. Move each along the steps: target, approach, pitch, checks, plan approval, sanction, payment, reports, renewal.")

T("official_docs", "Official documents (reference library)", [
    F("name", "Document", req=True), F("kind", "Kind", "list:doc_kind"), F("number", "Number or reference"), F("issued_on", "Issued on", "date"),
    F("valid_until", "Valid until (leave blank if it does not expire)", "date"), F("authority", "Issued by"), F("location", "Where the original is kept"),
    F("status", "Status", "enum:Have,Missing,Applied,Not applicable"), F("notes", "Notes", "area")],
  """SELECT t.id, t.name, t.kind, t.number, t.issued_on, t.valid_until, t.authority, t.location, t.status, t.notes, t.file_name, t.size,
     CASE WHEN COALESCE(t.file,'')<>'' THEN 'Y' ELSE 'N' END has_file,
     CASE WHEN t.status='Not applicable' THEN 'Not applicable'
          WHEN t.status='Missing' THEN 'Missing'
          WHEN t.status='Applied' THEN 'Applied'
          WHEN COALESCE(t.valid_until,'')<>'' AND t.valid_until<:today THEN 'Expired'
          WHEN COALESCE(t.valid_until,'')<>'' AND julianday(t.valid_until)-julianday(:today)<=60 THEN 'Expires soon'
          ELSE 'Have' END state FROM official_docs t""",
  [("name", "Document"), ("kind", "Kind"), ("number", "Number"), ("valid_until", "Valid until", "date"), ("has_file", "File attached", "yn"), ("state", "State", "badge")],
  FIN, read=FIN, search=["t.name", "kind", "number", "authority", "location"], order="t.kind, t.name", actions=["docfile"],
  hint="One place for every official paper funders ask for: registration, 12A, 80G, CSR-1, audited accounts and more. Attach the scanned file (PDF, photo or Word, up to 10 MB) and note the number and expiry. Press 'Add the standard list' once to start.")
