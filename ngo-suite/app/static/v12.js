// v12: social media planner. Ideas come from your own records; posting happens in your own social tools.
async function viewSocial() {
  const ideas = await get("/social/ideas"), projects = await get("/options/projects");
  const proj = h("select", {}, h("option", { value: "" }, "All our work"), ...projects.map(p => h("option", { value: p.id }, p.label)));
  const lang = h("select", {}, ...["English", "Hindi", "Marathi"].map(l => h("option", {}, l)));
  const cap = h("textarea", { rows: 6, placeholder: "Press 'Write a caption' to draft one from your records, then edit it." });
  const note = h("div", { class: "hint" });
  const draft = async () => { const r = await must(() => get(`/social/draft?project_id=${proj.value}&lang=${lang.value}`)); if (r) { cap.value = r.caption; note.textContent = r.note; } };
  const save = async (title, extra) => { const body = { title, caption: cap.value, language: lang.value, status: cap.value ? "Drafted" : "Idea", owner: USER.name || USER.username, project_id: proj.value || null, ...extra }; if (await must(() => post("/t/social_posts", body))) { toast("Saved as a draft. Open Social posts to continue."); } };
  const card = (i) => h("div", { class: "card", style: "margin-bottom:8px;display:flex;gap:12px;align-items:center;flex-wrap:wrap" },
    h("div", { style: "flex:1;min-width:240px" }, h("b", {}, i.title), h("div", { class: "hint" }, (i.kind) + " · " + (i.date || "") + " · " + i.why)),
    h("button", { class: "btn sm", onclick: async () => { proj.value = i.project_id || ""; await draft(); await save(i.title, { plan_date: i.date, media_id: i.media_id || null, status: "Drafted" }); } }, "Make a draft"));
  return h("div", {}, head("Post ideas", "Ideas taken from your own work. Nothing is posted from here: publish with Meta Business Suite, Buffer or the app itself."),
    h("div", { class: "card", style: "margin-bottom:12px" }, h("h2", {}, "Write a caption"),
      h("div", { style: "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px" }, proj, lang, h("button", { class: "btn pri", onclick: draft }, "Write a caption")), cap, note,
      h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => { cap.select(); copyText(cap.value); } }, "Copy"), h("button", { class: "btn", onclick: () => save("Caption " + new Date().toISOString().slice(0, 10), {}) }, "Save as a draft"))),
    ideas.items.length ? h("div", {}, h("h2", {}, "What to post about now"), ...ideas.items.map(card)) : h("div", { class: "empty" }, "No ideas right now. Add an event, record an activity with a photo that has consent, or set a project end date."));
}
