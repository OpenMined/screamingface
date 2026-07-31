"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Light/dark for the console.
 *
 * The vendored SFDS tokens key dark mode off `[data-theme="dark"]` on `<html>` and carry NO
 * `prefers-color-scheme` rule, so nothing happens unless something sets that attribute. This
 * module is that something.
 *
 * Default is dark, by operator preference (OME-709).
 */

export type Theme = "dark" | "light";

export const DEFAULT_THEME: Theme = "dark";
export const THEME_STORAGE_KEY = "aigateway-ui:theme";

/**
 * Put the stored theme on `<html>`.
 *
 * INVARIANT: this function closes over NOTHING. It is serialized with `.toString()` into a script
 * tag in the document head, and `.toString()` yields source without scope — so any module-level
 * identifier referenced here would be `undefined` in the browser. Minification renames those, so
 * the failure would not be visible when reading this file. Every literal is therefore inline, and
 * a test asserts the emitted source mentions none of the exported names.
 *
 * INVARIANT: it must not throw. Safari in private mode throws on `localStorage` access, and a
 * console that will not render because of a colour preference is worse than the wrong colour.
 */
export function applyStoredTheme(): void {
  try {
    const stored = window.localStorage.getItem("aigateway-ui:theme");
    const theme = stored === "light" || stored === "dark" ? stored : "dark";
    document.documentElement.setAttribute("data-theme", theme);
  } catch {
    document.documentElement.setAttribute("data-theme", "dark");
  }
}

/** The theme currently in effect, read from the element the tokens actually respond to. */
export function readTheme(): Theme {
  if (typeof document === "undefined") return DEFAULT_THEME;
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : DEFAULT_THEME;
}

/**
 * Subscribe to the attribute the tokens key off, so the switch reflects the DOM rather than a
 * private copy of it that could disagree.
 */
function subscribeToTheme(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => observer.disconnect();
}

export function ThemeSwitch() {
  /*
   * `useSyncExternalStore`, not `useState` + an effect.
   *
   * The theme lives on `<html>`, written by the served pre-paint script before React exists — it is
   * external mutable state, and this is the hook built for reading that without tearing. Syncing it
   * in an effect instead is both a lint error here (`react-hooks/set-state-in-effect`) and a real
   * flash: the effect runs after paint, so the label would render "Dark" and then correct itself.
   *
   * The server snapshot is the DEFAULT, which is all the server can know; the client snapshot reads
   * the element the script already set, so hydration converges without a mismatch warning.
   */
  const theme = useSyncExternalStore(subscribeToTheme, readTheme, () => DEFAULT_THEME);

  const toggle = useCallback(() => {
    const next: Theme = readTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // A preference that cannot be saved is still worth applying for this session.
    }
  }, []);

  const isDark = theme === "dark";

  return (
    <button
      type="button"
      className="theme-switch"
      onClick={toggle}
      aria-pressed={isDark}
      // The accessible name stays constant while the PRESSED state carries the meaning. A label
      // that swaps between "dark mode" and "light mode" makes a screen-reader user guess whether it
      // names the current state or the action.
      aria-label="Dark theme"
      title={isDark ? "Switch to light" : "Switch to dark"}
    >
      <span aria-hidden="true" className="theme-switch-icon">
        {isDark ? "◐" : "◑"}
      </span>
      <span className="theme-switch-text">{isDark ? "Dark" : "Light"}</span>
    </button>
  );
}
