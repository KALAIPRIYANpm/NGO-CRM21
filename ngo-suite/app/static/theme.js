/* Light, dark and accent colour. Stored only in this browser. Loaded first so there is no flash. */
(function () {
  const get = k => { try { return localStorage.getItem(k) || ""; } catch (e) { return ""; } };
  window.themeChoice = () => get("ngo_theme") || "auto";
  window.accentChoice = () => /^#[0-9a-fA-F]{6}$/.test(get("ngo_accent")) ? get("ngo_accent") : "";
  window.applyTheme = function () {
    const t = window.themeChoice(), dark = t === "dark" || (t === "auto" && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    const m = document.querySelector('meta[name="theme-color"]'); if (m) m.content = dark ? "#0f1a22" : "#0f5e63";
  };
  window.setThemeChoice = function (t, accent) {
    try { if (t) localStorage.setItem("ngo_theme", t); if (accent === "") localStorage.removeItem("ngo_accent"); else if (accent) localStorage.setItem("ngo_accent", accent); } catch (e) { /* storage blocked */ }
    window.applyTheme(); if (typeof applyBrand === "function") applyBrand({});
  };
  window.applyTheme();
  if (window.matchMedia) { try { matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => window.applyTheme()); } catch (e) { /* old browser */ } }
})();
