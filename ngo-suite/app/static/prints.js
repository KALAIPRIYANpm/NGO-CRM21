/* Printable A4 documents. Everything user-typed goes through esc(). */
"use strict";
function sheetHead(o) {
  return `${o.logo ? `<img src="${esc(o.logo)}" alt="" style="max-height:60px;max-width:220px;float:right">` : ""}<div class="org"><b>${esc(o.name)}</b><div>${esc(o.tagline)}</div><div>${esc([o.address, o.phone, o.email].filter(Boolean).join(" · "))}</div>${o.reg ? `<div>${esc(o.reg)}</div>` : ""}</div>`;
}
const sign = f => `<div class="sign"><div>${esc(f.sign_left || "")}</div><div>${esc(f.sign_right || "")}</div></div>`;
const fmtLines = f => [f.line1, f.line2, f.line3].filter(Boolean).map(x => `<p>${esc(x)}</p>`).join("");
const tbl = (head, rows, foot) => `<table><thead><tr>${head.map(x => `<th>${esc(x)}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${r.map((c, i) => `<td${typeof c === "string" && c.startsWith("₹") ? ' style="text-align:right"' : ""}>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody>${foot ? `<tfoot>${foot}</tfoot>` : ""}</table>`;

function renderPrint(p) {
  const o = p.org, f = p.format || {};
  const k = p.kind;
  if (k === "receipt") { const d = p.donation, dn = p.donor;
    return sheetHead(o) + `<h1>${esc(f.title)}</h1>
    <div class="row"><div><b>Receipt no:</b> ${esc(d.receipt_no)}</div><div><b>Date:</b> ${fd(d.date)}</div></div>
    <p>${esc(f.line1)}</p>
    <div class="row"><div><b>Received from:</b> ${esc(dn.name)}<br><span class="small">${esc([dn.city, dn.phone].filter(Boolean).join(" · "))}${dn.id_no ? "<br>ID: " + esc(dn.id_no) : ""}</span></div><div style="text-align:right"><div class="small">Amount received</div><div class="amt">${money(d.amount)}</div></div></div>
    <p><b>Rupees:</b> ${esc(p.words)}</p>
    <div class="row"><div><b>Purpose:</b> ${esc(d.purpose || "General")}</div><div><b>Fund type:</b> ${esc(d.fund_type || "")}</div></div>
    <div class="row"><div><b>Mode:</b> ${esc(d.mode || "")}</div><div><b>Reference:</b> ${esc(d.reference || "–")}</div></div>
    <p class="small">${esc(f.line2)}</p><p>${esc(f.line3)}</p>${sign(f)}`; }
  if (k === "record") { const r = p.record;
    return sheetHead(o) + `<h1>${esc(f.title)}</h1>
    <div class="row"><div><b>Record no:</b> ${esc(r.record_no)}</div><div><b>Date:</b> ${fd(r.date)}</div></div>
    <div class="row"><div><b>To / party:</b> ${esc(r.party || "")}<br><span class="small">${esc([r.address, r.phone].filter(Boolean).join(" · "))}</span></div><div style="text-align:right"><b>Project:</b> ${esc(r.project || "–")}<br><b>Fund or purpose:</b> ${esc(r.purpose || "–")}<br><b>Period or ref:</b> ${esc(r.period_ref || "–")}</div></div>
    ${fmtLines(f)}
    ${f.show_lines === "Y" && p.lines.length ? tbl(["Item", "Detail", "Qty", "Unit", "Times", ...(f.show_amounts === "Y" ? ["Rate", "Amount"] : [])], p.lines.map(l => [l.item, l.detail, num(l.qty), l.unit || "", num(l.times), ...(f.show_amounts === "Y" ? [money(l.rate), money(l.amount)] : [])]),
      f.show_amounts === "Y" ? `<tr><td colspan="6"><b>Total</b></td><td style="text-align:right"><b>${money(p.lines_total)}</b></td></tr>` : "") : ""}
    ${f.show_amounts === "Y" ? `<div class="row" style="margin-top:12px"><div><b>Amount:</b> ${money(r.amount)}<br><b>Received:</b> ${money(r.received)}<br><b>Balance:</b> ${money(r.balance)}</div><div style="text-align:right">${r.amount ? `<span class="small">${esc(p.words)}</span>` : ""}${o.upi && r.balance > 0 ? `<br><img src="/api/qr.svg?text=${encodeURIComponent(upiLink(o, r.balance))}" alt="UPI QR" style="width:110px;height:110px"><br><b>Pay by UPI:</b> ${esc(o.upi)}` : ""}</div></div>` : ""}
    ${r.people ? `<p><b>People:</b> ${IN.format(r.people)}</p>` : ""}${r.next_date ? `<p><b>Next date:</b> ${fd(r.next_date)}</p>` : ""}${sign(f)}`; }
  if (k === "statement") { const d = p.donor;
    return sheetHead(o) + `<h1>${esc(f.title)}</h1><div class="row"><div><b>Donor:</b> ${esc(d.name)} (${esc(d.code)})<br><span class="small">${esc([d.city, d.phone].filter(Boolean).join(" · "))}</span></div><div><b>As on:</b> ${fd(p.asof)}</div></div>${fmtLines(f)}
    ${p.gifts.length ? tbl(["Receipt", "Date", "Purpose", "Mode", "Amount"], p.gifts.map(g => [g.receipt_no, fd(g.date), g.purpose || "", g.mode || "", money(g.amount)]), `<tr><td colspan="4"><b>Total received</b></td><td style="text-align:right"><b>${money(p.total)}</b></td></tr>`) : "<p>No gifts recorded.</p>"}${sign(f)}`; }
  if (k === "voucher") { const e = p.entry;
    return sheetHead(o) + `<h1>${esc(f.title)}</h1><div class="row"><div><b>Voucher no:</b> ${esc(e.voucher_no || "")}</div><div><b>Date:</b> ${fd(e.date)}</div></div>${fmtLines(f)}
    ${tbl(["Paid to / party", "Head", "Fund", "Mode", "Amount"], [[e.party || "", e.head || "", e.fund, e.mode || "", money(e.amount)]])}<p><b>Rupees:</b> ${esc(p.words)}</p>${e.note ? `<p class="small">${esc(e.note)}</p>` : ""}${sign(f)}`; }
  if (k === "utilisation") { const g = p.grant;
    return sheetHead(o) + `<h1>${esc(f.title)}</h1><p>${esc(f.line1)}</p>
    <div class="row"><div><b>Grant:</b> ${esc(g.code)} · ${esc(g.funder)}<br><b>Project:</b> ${esc(g.project || "–")}</div><div style="text-align:right"><b>Period:</b> ${fd(g.start)} to ${fd(g.end)}<br><b>As on:</b> ${fd(p.asof)}</div></div>
    <div class="row"><div><b>Sanctioned:</b> ${money(g.sanctioned)}</div><div><b>Received:</b> ${money(g.received)}</div><div><b>Spent:</b> ${money(g.spent)}</div><div><b>Unspent balance:</b> ${money(g.in_hand)}</div></div>
    <h3>Money received</h3>${p.instalments.length ? tbl(["Date", "Reference", "Amount"], p.instalments.map(i => [fd(i.date), i.reference || "", money(i.amount)])) : "<p>None yet.</p>"}
    <h3 style="margin-top:12px">Money spent, by head</h3>${p.heads.length ? tbl(["Head", "Payments", "Amount"], p.heads.map(x => [x.head, String(x.n), money(x.amount)]), `<tr><td colspan="2"><b>Total spent</b></td><td style="text-align:right"><b>${money(g.spent)}</b></td></tr>`) : "<p>None yet.</p>"}
    <p class="small" style="margin-top:10px">${esc(f.line2)} ${esc(f.line3)}</p>${sign(f)}`; }
  if (k === "activity") { const a = p.activity;
    return sheetHead(o) + `<h1>${esc(f.title)}</h1><p>${esc(f.line1)}</p>${tbl(["Date", "Project", "Activity", "Place"], [[fd(a.date), a.project, a.activity || "", a.village || ""]])}
    <div class="row" style="margin-top:10px"><div><b>People reached:</b> ${IN.format(a.people_reached)}</div><div><b>Volunteers:</b> ${a.volunteers}</div><div><b>Spent:</b> ${money(a.spent)}</div><div><b>Cost per person:</b> ${money(a.cost_per_person)}</div></div>
    ${a.note ? `<p><b>Note:</b> ${esc(a.note)}</p>` : ""}<p class="small">${esc(f.line2)} ${esc(f.line3)}</p>${sign(f)}`; }
  if (k === "proposal") { const t = p;
    return sheetHead(t.org) + `<h1>PROPOSAL BUDGET</h1><div class="row"><div><b>Project:</b> ${esc(t.project)}<br><b>Funder:</b> ${esc(t.funder || "–")}</div><div style="text-align:right"><b>People:</b> ${IN.format(t.people || 0)}<br><b>Months:</b> ${t.months}</div></div>
    ${tbl(["Line", "Group", "Qty", "Unit cost", "Times", "Amount"], t.lines.map(l => [l.line, l.grp || "", num(l.qty), money(l.unit_cost), num(l.times), money(l.amount)]))}
    <table style="margin-top:10px;width:60%;margin-left:auto"><tbody>${[["Lines total", t.lines_total], ["Contingency", t.contingency], ["Project budget", t.subtotal], [`Overhead ${pct(t.overhead_pct)}`, t.overhead], ["Total with overhead", t.gross], [`Own share ${pct(t.own_pct)}`, -t.own_share], ["Amount asked from funder", t.ask], ...(t.gst ? [["GST", t.gst], ["Amount asked with GST", t.ask_with_gst]] : [])].map(([l, v], i, a) => `<tr><td${i === 6 ? " style='font-weight:700'" : ""}>${esc(l)}</td><td style="text-align:right${i === 6 ? ";font-weight:700" : ""}">${money(v)}</td></tr>`).join("")}</tbody></table>
    <p class="small" style="margin-top:12px">Planning figures from our own records. GST shown only if registered; check with your CA.</p>${sign({ sign_left: "Prepared by", sign_right: "For the organisation" })}`; }
  if (k === "payslip") { const m = p.member, c = p.counts;
    return sheetHead(o) + `<h1>SALARY SLIP</h1><div class="row"><div><b>Name:</b> ${esc(m.name)} (${esc(m.code)})<br><span class="small">${esc(m.role || "")}</span></div><div style="text-align:right"><b>Month:</b> ${esc(fm(p.month))}<br><b>Pay type:</b> ${esc(m.pay_type)} · ${money(m.pay_rate)}</div></div>
    ${tbl(["Item", "Detail", "Amount"], [...(p.salary ? [["Monthly pay", "", money(p.salary)]] : []), ...(m.pay_type === "Per day" ? [["Days worked", `${num(p.days_present)} days (Present ${c.P || 0}, Half ${c.H || 0}, Absent ${c.A || 0}, Leave ${c.L || 0}); extra hours ${num(p.extra_hours)} at ${money(p.extra_hour_rate)}`, money(p.daily_pay)]] : []), ["Travel and food paid back", "", money(p.travel_paid)]],
      `<tr><td colspan="2"><b>Total due</b></td><td style="text-align:right"><b>${money(p.due)}</b></td></tr><tr><td colspan="2">Less advances already paid</td><td style="text-align:right">${money(-p.advances)}</td></tr><tr><td colspan="2"><b>Net payable</b></td><td style="text-align:right"><b>${money(p.net)}</b></td></tr>`)}
    <p><b>Rupees:</b> ${esc(p.words)}</p>${m.bank_account ? `<p class="small">Bank account: ${esc(m.bank_account)} · IFSC ${esc(m.ifsc || "")}</p>` : ""}${sign({ sign_left: "Received by", sign_right: "Authorised signatory" })}`; }
  if (k === "poster") return sheetHead(o) + `<h1 style="font-size:28px;text-align:center">Support our work</h1><p style="text-align:center;font-size:16px">${esc(p.message || "")}</p>
    <div style="text-align:center;margin:20px 0"><img src="${p.qr}" alt="UPI QR code" style="width:300px;height:300px"><div style="font-size:18px;margin-top:8px"><b>${esc(o.upi)}</b></div><div class="small">Scan with any UPI app</div></div>
    <p style="text-align:center">${esc([o.phone, o.email].filter(Boolean).join(" · "))}</p>`;
  return "<p>Nothing to print.</p>";
}
const upiLink = (o, amt) => o.upi ? `upi://pay?pa=${encodeURIComponent(o.upi).replace("%40", "@")}&pn=${encodeURIComponent(o.name)}${amt ? "&am=" + amt : ""}&cu=INR` : "";
async function showPrint(kind, id, format, month) {
  let p;
  if (kind === "proposal") p = { ...id, kind: "proposal" };
  else if (kind === "payslip") p = await must(() => get(`/print/payslip/${id}?month=${month}`));
  else if (kind === "poster") p = id;
  else p = await must(() => get(`/print/${kind}/${id}` + (format ? "?format=" + encodeURIComponent(format) : "")));
  if (!p) return;
  const close = () => { ov.remove(); document.body.classList.remove("ov"); };
  const sheet = h("div", { class: "sheet" }); sheet.innerHTML = renderPrint(p);
  const ov = h("div", { class: "overlay" }, h("div", { class: "printbar" }, h("button", { class: "btn", onclick: close }, "Close"), h("button", { class: "btn pri", onclick: () => window.print() }, "Print / save as PDF")), sheet);
  $("#print-root").append(ov); document.body.classList.add("ov");
}
boot();
