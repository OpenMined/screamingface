/**
 * The theme's whole difficulty is WHEN it is applied, not what it does.
 *
 * A React effect runs after first paint, so a theme applied there renders light and then flips —
 * visibly, on every navigation. `applyStoredTheme` therefore runs synchronously in the document
 * head before anything paints. It is serialized into that script tag via `.toString()`, so the
 * thing shipped to the browser IS the function tested here rather than a string written alongside
 * it that could drift.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { fireEvent, render, screen } from "@testing-library/react";

import {
  DEFAULT_THEME,
  THEME_STORAGE_KEY,
  ThemeSwitch,
  applyStoredTheme,
  readTheme,
} from "./theme";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("applying the stored theme before paint", () => {
  it("defaults to dark when nothing has been chosen", () => {
    applyStoredTheme();

    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("honours a stored choice over the default", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "light");

    applyStoredTheme();

    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("ignores a stored value that is not a theme", () => {
    // Storage is user-writable. A junk value must fall back rather than land on the element, where
    // it would match no token block and leave the page unstyled.
    localStorage.setItem(THEME_STORAGE_KEY, "chartreuse");

    applyStoredTheme();

    expect(document.documentElement.getAttribute("data-theme")).toBe(DEFAULT_THEME);
  });

  it("survives storage being unavailable", () => {
    // Safari in private mode throws on access. A console that will not render because of a theme
    // preference is a worse outcome than the wrong theme.
    const original = Object.getOwnPropertyDescriptor(window, "localStorage");
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new Error("denied");
      },
    });

    expect(() => applyStoredTheme()).not.toThrow();
    expect(document.documentElement.getAttribute("data-theme")).toBe(DEFAULT_THEME);

    if (original) Object.defineProperty(window, "localStorage", original);
  });
});

describe("the served pre-paint script", () => {
  // public/theme-init.js is what the browser actually runs before first paint. It mirrors
  // `applyStoredTheme`, and these assertions are what stop the two drifting apart silently — a
  // mismatch would show up only as a flash of the wrong theme, which nobody files a bug about.
  // `import.meta.url` is a vite dev-server URL under jsdom, not a file: URL, so it cannot be
  // handed to readFileSync. cwd is the app root when vitest runs.
  const served = readFileSync(path.resolve("public/theme-init.js"), "utf8");

  it("agrees on the storage key", () => {
    expect(served).toContain(THEME_STORAGE_KEY);
    expect(applyStoredTheme.toString()).toContain(THEME_STORAGE_KEY);
  });

  it("agrees that the default is dark", () => {
    expect(DEFAULT_THEME).toBe("dark");
    // The literal, not the constant: the served file cannot import anything.
    expect(served).toMatch(/:\s*"dark"/);
  });

  it("writes the attribute the OMDS tokens actually respond to", () => {
    expect(served).toContain('setAttribute("data-theme"');
  });

  it("cannot throw when storage is unavailable", () => {
    expect(served).toContain("catch");
  });

  it("closes over nothing, so it can run standalone", () => {
    // It is served as a bare file with no module scope, so any identifier from theme.tsx would be
    // undefined in the browser.
    expect(served).not.toContain("DEFAULT_THEME");
    expect(served).not.toContain("THEME_STORAGE_KEY");
  });
});

describe("readTheme", () => {
  it("reports the default before anything is chosen", () => {
    expect(readTheme()).toBe(DEFAULT_THEME);
  });

  it("reports what is on the element", () => {
    document.documentElement.setAttribute("data-theme", "light");

    expect(readTheme()).toBe("light");
  });
});

describe("the switch", () => {
  it("flips the document to light", () => {
    applyStoredTheme();
    render(<ThemeSwitch />);

    fireEvent.click(screen.getByRole("button", { name: /theme/i }));

    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("persists the choice so a reload keeps it", () => {
    applyStoredTheme();
    render(<ThemeSwitch />);

    fireEvent.click(screen.getByRole("button", { name: /theme/i }));

    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
  });

  it("flips back", () => {
    applyStoredTheme();
    render(<ThemeSwitch />);
    const button = screen.getByRole("button", { name: /theme/i });

    fireEvent.click(button);
    fireEvent.click(button);

    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("tells assistive technology which state it is in", () => {
    // A pressed-state toggle, not a link: the control means "dark is on", and a screen reader needs
    // that state rather than a label that changes out from under it.
    applyStoredTheme();
    render(<ThemeSwitch />);

    expect(screen.getByRole("button", { name: /theme/i })).toHaveAttribute("aria-pressed", "true");
  });
});
