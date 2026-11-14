/* Impact cards (shareable donor page) and the year-end compliance pack. */
"use strict";
const prevMonthISO = () => { let [y, m] = asofISO().slice(0, 7).split("-").map(Number); m -= 1; if (m < 1) { m = 12; y -= 1; } return y + "-" + String(m).padStart(2, "0"); };   // string maths: no time-zone shifts

async function viewCards() {
  if (!["admin", "accountant", "programme"].includes(USER.role)) return h("div", {}, head("Impact cards"), h("div", { class: "card" }, "Not available for your role."));
  const publish = USER.role !== "programme";
  const proj = await get("/options/projects");
  const pSel = h("select", {}, ...proj.map(p => h("option", { value: p.id }, p.label || p.name))), month = h("input", { type: "month", value: prevMonthISO() });
  const area = h("div", {}), list = h("div", {});
  let sel = new Set();
  const preview = async () => {
    const d = await must(() => get(`/cards/preview?project_id=${pSel.value}&month=${month.value}`)); if (!d) return;
    sel = new Set(d.photos.slice(0, 2).map(p => p.id));
    const head1 = h("input", { value: d.suggested_headline, maxlength: 120 }), story = h("textarea", { rows: 4, maxlength: 700, placeholder: "One real moment from this month: who, what changed. Use first names only, and only with permission." });
    const stat = (n, l) => h("div", { class: "card", style: "text-align:center" }, h("div", { style: "font-size:26px;font-weight:700;color:var(--brand)" }, n), h("div", { class: "hint" }, l));
    const photos = d.photos.length ? h("div", { class: "shots" }, ...d.photos.map(p => { const b = h("div", { class: "shot", tabindex: 0, role: "checkbox", "aria-checked": sel.has(p.id), style: "cursor:pointer;outline:" + (sel.has(p.id) ? "3px solid var(--brand)" : "none") },
      h("img", { src: `/api/media/${p.id}/thumb`, alt: p.caption || "Photo", loading: "lazy" }));
      const tog = () => { if (sel.has(p.id)) sel.delete(p.id); else if (sel.size < 4) sel.add(p.id); else return toast("Choose up to 4 photos", true); b.style.outline = sel.has(p.id) ? "3px solid var(--brand)" : "none"; b.setAttribute("aria-checked", sel.has(p.id)); };
      b.onclick = tog; b.onkeydown = e => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); tog(); } }; return b; }))
      : h("div", { class: "hint" }, "No photos with consent for this project and month. Photos appear here only when everyone shown agreed (ticked when uploading, or changed in the gallery).");
    area.replaceChildren(h("div", { class: "card" }, h("h2", {}, d.project + " · " + d.month_label),
      h("div", { class: "tiles", style: "grid-template-columns:repeat(auto-fit,minmax(130px,1fr));margin:8px 0" }, stat(num(d.people), "people reached"), stat(d.activities, "activities"), stat(num(d.volunteers), "volunteer places"), stat(money(d.spent), "spent"), stat(d.per_person != null ? money(d.per_person) : "–", "per person")),
      d.activities ? null : h("div", { class: "qbar warn" }, "No activities were logged for this month. Log them in the field app, or write a story below."),
      h("label", {}, "Headline"), head1, h("label", { style: "margin-top:8px" }, "Story (optional)"), story, h("label", { style: "margin-top:8px" }, "Photos (consented only, up to 4)"), photos,
      publish ? h("div", { class: "actions" }, h("button", { class: "btn pri", onclick: async () => {
        const r = await must(() => post("/cards", { project_id: +pSel.value, month: month.value, headline: head1.value, story: story.value, photo_ids: [...sel] })); if (!r) return;
        const full = location.origin + r.url; drawList();
        const msg = `Dear {first_name}, thank you for standing with ${META.settings.org_name || "us"}. Here is what your support achieved in ${d.month_label}: ${full}`;
        const close = modal("Card ready to share", h("div", {}, h("p", {}, "Anyone with this link can see the card, but nothing else in your software. You can switch it off at any time."), h("input", { value: full, readonly: true, onfocus: e => e.target.select() }),
          h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => navigator.clipboard && navigator.clipboard.writeText(full).then(() => toast("Link copied")) }, "Copy link"), h("a", { class: "btn", href: r.url, target: "_blank", rel: "noopener" }, "Open"),
            h("button", { class: "btn pri", onclick: () => { try { sessionStorage.setItem("ngo_prefill", JSON.stringify({ name: "Impact card " + d.month_label + " " + d.project, body: msg })); } catch (e) { /* ignore */ } close(); location.hash = "#/r/messages"; } }, "Send to donors…"))));
      } }, "Create share link")) : h("div", { class: "hint", style: "margin-top:8px" }, "Only an administrator or the accounts officer can publish a card.")));
  };
  async function drawList() {
    if (!publish) return list.replaceChildren();
    const rows = await get("/cards");
    list.replaceChildren(h("h2", { style: "margin-top:18px" }, "Cards you have shared"), rows.length ? h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ...["Project", "Month", "Headline", "Photos", "Opened", "Status", ""].map(x => h("th", {}, x)))), h("tbody", {}, ...rows.map(r => h("tr", {},
      h("td", {}, r.project), h("td", {}, r.month), h("td", {}, r.headline), h("td", { class: "n" }, r.photos), h("td", { class: "n" }, r.views + (r.last_view ? " · last " + fd(r.last_view) : "")), h("td", {}, r.revoked ? h("span", { class: "badge b-red" }, "Switched off") : h("span", { class: "badge b-green" }, "Live")),
      h("td", {}, !r.revoked ? [h("a", { class: "btn sm", href: r.url, target: "_blank", rel: "noopener" }, "Open"), " ", h("button", { class: "btn sm", onclick: () => confirmBox("Switch this link off? People who have it will see 'no longer available'.", async () => { if (await must(() => post(`/cards/${r.id}/revoke`))) { toast("Switched off"); drawList(); } }, "Switch off") }, "Switch off")] : null)))))) : h("div", { class: "empty" }, "None yet."));
  }
  await drawList();
  return h("div", {}, head("Impact cards", "One page per project per month, built from what the field logged, for your donors. Photos need consent."), h("div", { class: "bar" }, pSel, month, h("button", { class: "btn pri", onclick: preview }, "Build card")), area, list);
}

/* ---------------- compliance pack ---------------- */
async function viewPack() {
  if (!["admin", "accountant"].includes(USER.role)) return h("div", {}, head("Audit and 80G pack"), h("div", { class: "card" }, "Ask an administrator or the accounts officer."));
  const out = h("div", {}), fy = h("select", {});
  const base = new Date(asofISO()).getFullYear(); for (let y = base; y >= base - 4; y--) fy.append(h("option", { value: y }, `${y}-${String(y + 1).slice(2)}`));
  const draw = async () => {
    const r = await must(() => get("/pack/readiness?fy=" + fy.value)); if (!r) return;
    const bad = r.items.filter(i => i.bad).length;
    const donor = h("select", {}, ...r.donors.map(d => h("option", { value: d.id }, `${d.name} (${d.code})`)));
    out.replaceChildren(
      h("div", { class: "qbar " + (bad ? "warn" : "") }, h("b", {}, bad ? `${bad} thing(s) to fix before you file or send documents` : "Nothing found to fix"), `  ·  ${r.donations} donations, ${money(r.total)} in ${r.label}`),
      h("div", { class: "card", style: "margin-bottom:12px" }, h("h2", {}, "Readiness check"), ...r.items.map(i => h("div", { style: "display:flex;gap:10px;align-items:flex-start;padding:7px 0;border-top:1px solid var(--line)" },
        h("span", { class: "badge b-" + (i.bad ? "amber" : "green"), style: "flex:none;min-width:54px;text-align:center" }, i.bad ? i.bad + " to fix" : "OK"),
        h("div", { style: "flex:1" }, i.label, i.detail ? h("div", { class: "hint" }, i.detail) : null), i.bad ? h("a", { href: i.link, class: "btn sm" }, "Open") : null))),
      h("div", { class: "card", style: "margin-bottom:12px" }, h("h2", {}, "For the auditor"), h("p", { class: "hint" }, "A zip with the donation register, cash book, fund summary, grant instalments and spend, expense claims with their bill photos, and a draft utilisation statement for every grant."),
        h("div", { class: "actions" }, h("a", { class: "btn pri", href: "/api/pack/audit-pack?fy=" + fy.value }, "Download audit pack (zip)"), h("a", { class: "btn", href: "/api/pack/register.csv?fy=" + fy.value }, "Donation register (CSV)"))),
      h("div", { class: "card", style: "margin-bottom:12px" }, h("h2", {}, "80G donor statement"), h("p", { class: "hint" }, "One page per donor for the year, with PAN, every receipt and the total. Opens in a new tab: print or save as PDF."),
        r.donors.length ? h("div", { class: "actions" }, donor, h("button", { class: "btn pri", onclick: () => window.open(`/api/pack/donor/${donor.value}?fy=${fy.value}`, "_blank", "noopener") }, "Open statement")) : h("div", { class: "empty" }, "No donations in this year.")),
      h("div", { class: "card" }, h("h2", {}, "Utilisation statements"), h("p", { class: "hint" }, "For grants running in this year: funds received, used by head, balance, with a place for your CA's signature."),
        r.grants.length ? h("div", { class: "tablewrap" }, h("table", {}, h("tbody", {}, ...r.grants.map(g => h("tr", {}, h("td", {}, g.code), h("td", {}, g.funder), h("td", {}, fd(g.start) + " to " + fd(g.end)), h("td", {}, h("a", { class: "btn sm", href: `/api/pack/uc/${g.id}`, target: "_blank", rel: "noopener" }, "Open"))))))) : h("div", { class: "empty" }, "No grants in this year.")),
      h("p", { class: "hint", style: "margin-top:12px" }, "These are drafts built from your records. They are not legal or tax advice, and cash-gift and 80G rules change. Your Chartered Accountant must check and certify before anything is issued or filed."));
  };
  fy.onchange = draw; await draw();
  return h("div", {}, head("Audit and 80G pack", "Year-end paperwork from the records you already keep."), h("div", { class: "bar" }, h("label", {}, "Financial year"), fy), out);
}
