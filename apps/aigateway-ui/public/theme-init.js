/*
 * Applies the stored theme before the page paints.
 *
 * WHY a served file rather than an inline script: this must run parser-blocking in <head> — a
 * React effect runs AFTER first paint, so the page would render light and then flip, visibly, on
 * every navigation. Serving it means the document contains no injected HTML at all, so a future
 * Content-Security-Policy needs no 'unsafe-inline'.
 *
 * This mirrors `applyStoredTheme` in src/app/theme.tsx, which is the tested implementation.
 * `theme.test.tsx` asserts the two agree on the storage key, the default, and the attribute, so
 * they cannot drift apart silently.
 *
 * Must never throw: Safari in private mode throws on localStorage access, and a console that will
 * not render because of a colour preference is worse than the wrong colour.
 */
(function () {
  try {
    var stored = window.localStorage.getItem("aigateway-ui:theme");
    var theme = stored === "light" || stored === "dark" ? stored : "dark";
    document.documentElement.setAttribute("data-theme", theme);
  } catch {
    document.documentElement.setAttribute("data-theme", "dark");
  }
})();
