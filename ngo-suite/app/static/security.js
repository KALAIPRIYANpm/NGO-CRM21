/* Two-step sign-in screens, sign out everywhere. */
"use strict";
function svgNode(text) { return new DOMParser().parseFromString(text, "image/svg+xml").documentElement; }

/* Walks a person through turning on two-step sign-in. Calls onDone() after the backup codes were shown. */
async function twoStepSetup(box, onDone) {
  const r = await must(() => post("/2fa/setup")); if (!r) return;
  const code = h("input", { inputmode: "numeric", autocomplete: "one-time-code", maxlength: 7, placeholder: "6-digit code", style: "font-size:20px;letter-spacing:4px;text-align:center" });
  const go = async () => {
    const res = await must(() => post("/2fa/enable", { code: code.value })); if (!res) return;
    const txt = res.codes.join("\n");
    box.replaceChildren(h("h2", {}, "Two-step sign-in is on"), h("p", {}, "Save these backup codes now. Each one works once if you lose your phone. They are shown only this time."),
      h("pre", { style: "background:#f3f1ec;padding:12px;border-radius:8px;font-size:16px;line-height:1.7" }, txt),
      h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => { const a = h("a", { href: URL.createObjectURL(new Blob([txt + "\n"], { type: "text/plain" })), download: "backup-codes.txt" }); document.body.append(a); a.click(); a.remove(); } }, "Download"),
        h("button", { class: "btn", onclick: () => navigator.clipboard && navigator.clipboard.writeText(txt).then(() => toast("Copied")) }, "Copy"), h("button", { class: "btn pri", onclick: onDone }, "I saved them")));
  };
  code.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  box.replaceChildren(h("h2", {}, "Turn on two-step sign-in"),
    h("p", {}, "1. Install an authenticator app on your phone (Google Authenticator, Microsoft Authenticator, Authy or similar)."), h("p", {}, "2. In the app choose Add account, then scan this picture:"),
    h("div", { style: "background:#fff;display:inline-block;padding:8px;border-radius:8px;border:1px solid var(--line)" }, svgNode(r.qr)),
    h("p", { class: "hint" }, "Cannot scan? Type this key into the app instead: ", h("b", { style: "word-break:break-all" }, r.secret.replace(/(.{4})/g, "$1 ").trim())),
    h("p", {}, "3. Type the 6-digit code the app shows:"), code, h("div", { class: "actions" }, h("button", { class: "btn pri", onclick: go }, "Turn on")));
  code.focus();
}

async function twoStepModal() {
  const st = await must(() => get("/2fa")); if (!st) return;
  const box = h("div", {});
  const draw = async () => {
    const s = await get("/2fa");
    if (!s.enabled) { box.replaceChildren(h("h2", {}, "Two-step sign-in"), h("p", {}, "Adds a code from your phone to the password. Even if someone learns your password, they cannot get in. Recommended for administrators and finance users."), h("div", { class: "actions" }, h("button", { class: "btn pri", onclick: () => twoStepSetup(box, async () => { await draw(); toast("Two-step sign-in is on"); }) }, "Set up")), signoutAll()); return; }
    const pw = h("input", { type: "password", placeholder: "Your password" }), code = h("input", { inputmode: "numeric", placeholder: "Current code or a backup code" });
    box.replaceChildren(h("h2", {}, "Two-step sign-in"), h("p", {}, h("span", { class: "badge b-green" }, "On"), ` ${s.backup_left} backup code(s) left.`),
      s.required ? h("p", { class: "hint" }, "Your organisation requires this for administrators, so it cannot be turned off.") : h("div", {}, h("h3", {}, "Turn off"), pw, code, h("div", { class: "actions" }, h("button", { class: "btn", onclick: async () => { if (await must(() => post("/2fa/disable", { password: pw.value, code: code.value }))) { toast("Turned off"); draw(); } } }, "Turn off"))), signoutAll());
  };
  const signoutAll = () => h("div", { style: "margin-top:14px;border-top:1px solid var(--line);padding-top:10px" }, h("div", { class: "hint" }, "Lost a phone or used a shared computer? End every session of yours, everywhere."),
    h("button", { class: "btn", onclick: async () => { if (await must(() => post("/logout-all"))) { USER = null; showLogin(); } } }, "Sign out everywhere"));
  modal("Security", box); await draw();
}

/* Shown instead of the app when the organisation requires two-step sign-in and this administrator has not set it up. */
function forceTwoStep() {
  const box = h("div", {});
  $("#app").replaceChildren(h("div", { class: "card login", style: "max-width:460px" }, h("div", { class: "hint" }, "Your organisation requires two-step sign-in for administrators."), box,
    h("div", { style: "margin-top:12px" }, h("button", { class: "btn sm", onclick: async () => { await post("/logout"); USER = null; showLogin(); } }, "Sign out"))));
  twoStepSetup(box, () => location.reload());
}

/* Second screen of sign-in: the 6-digit code. */
function askCode(pre) {
  const code = h("input", { inputmode: "text", autocomplete: "one-time-code", autofocus: true, placeholder: "123456", style: "font-size:22px;letter-spacing:4px;text-align:center" });
  const go = async () => { try { await post("/login/2fa", { pre, code: code.value }); await boot(); } catch (e) { toast(e.message, true); if (e.status === 401 && /timed out|Sign in/i.test(e.message) || e.status === 429) showLogin(); } };
  code.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  $("#app").replaceChildren(h("div", { class: "card login" }, h("h1", {}, BRAND.product), h("div", { class: "sub" }, "Two-step sign-in"), h("p", {}, "Open your authenticator app and type the 6-digit code. Lost your phone? Type one of your backup codes."),
    h("div", { class: "f" }, h("label", {}, "Code"), code), h("button", { class: "btn pri", onclick: go }, "Continue"), h("div", { style: "margin-top:10px" }, h("button", { class: "btn sm", onclick: showLogin }, "Back"))));
  code.focus();
}
