/* VENDORED from screamingface-brand@c9673b3 (public/theme.js) — do not edit here. Re-copy to update. */
/* Light/dark toggle. Default follows the OS; choice persists per browser.
   The no-flash initial set happens inline in <head>; this only wires the
   button and keeps the label in sync. */
(function () {
  function label(t) { return t === "dark" ? "◐ dark" : "◐ light"; }
  function current() { return document.documentElement.getAttribute("data-theme") || "light"; }
  function apply(t) {
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("sf_theme", t); } catch (e) {}
    var b = document.getElementById("theme-toggle");
    if (b) b.textContent = label(t);
  }
  document.addEventListener("DOMContentLoaded", function () {
    var b = document.getElementById("theme-toggle");
    if (b) {
      b.textContent = label(current());
      b.addEventListener("click", function () {
        apply(current() === "dark" ? "light" : "dark");
      });
    }
  });
})();
