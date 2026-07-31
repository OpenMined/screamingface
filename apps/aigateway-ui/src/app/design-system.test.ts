/**
 * The SFDS v2 rules this console must not drift from (OME-716).
 *
 * These read the app's own CSS as text rather than rendering it. That is the point: the rules are
 * about what the source is ALLOWED to say, and a rendered snapshot cannot tell you that a
 * developer reached for gold — only that today's pixels happen to look right.
 *
 * Every assertion here corresponds to a stated v2 anti-rule, and each one is a mistake that would
 * otherwise pass code review, pass the type checker, pass all 181 behavioural tests, and look
 * completely fine in a screenshot.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const APP = join(import.meta.dirname, "..");

/** Every stylesheet the app OWNS. The vendored token file is excluded on purpose — it is the one
 *  place literal values and the full gold ladder legitimately live. */
const AUTHORED_CSS = [
  "app/globals.css",
  "app/accounts/[id]/detail.module.css",
  "app/accounts/[id]/credentials/new/form.module.css",
  "brand/tokens/base.css",
] as const;

function read(relative: string): string {
  return readFileSync(join(APP, relative), "utf8");
}

/** CSS with comments stripped, so a rule discussed in prose is not mistaken for a rule applied. */
function declarations(relative: string): string {
  return read(relative).replace(/\/\*[\s\S]*?\*\//g, "");
}

describe("SFDS v2 · the app register", () => {
  // The single most likely way to get this surface wrong: "gold is the ScreamingFace colour", so
  // paint the console gold. In v2 gold is --brand/--gain and it is rationed to THE WIN — the
  // leading leaderboard row, the SOTA counter. An admin console has no win.
  it.each(AUTHORED_CSS)("%s references no gold token", (file) => {
    const css = declarations(file);
    expect(css).not.toMatch(/var\(--brand-/);
    expect(css).not.toMatch(/var\(--gain-/);
    // The v1 bridge names still resolve, and --gain in particular now resolves to GOLD where v1
    // had it green — so a v1 habit silently changes meaning rather than breaking.
    expect(css).not.toMatch(/var\(--gain\)/);
    expect(css).not.toMatch(/var\(--mark\)/);
  });

  it("uses the accent (blue) for interaction", () => {
    const css = declarations("app/globals.css");
    expect(css).toMatch(/var\(--accent-solid\)/);
    expect(css).toMatch(/var\(--accent-focus-ring\)/);
  });

  it("uses --success, not --gain, for the healthy state", () => {
    const css = declarations("app/globals.css");
    expect(css).toMatch(/var\(--success-/);
  });
});

describe("SFDS v2 · anti-rules", () => {
  // "Corner radius: --radius-none (square corners everywhere except window chrome)." This app has
  // no window chrome, so every radius must be the zero token — and --radius-window must not appear.
  it.each(AUTHORED_CSS)("%s introduces no rounded corner", (file) => {
    const css = declarations(file);
    for (const [, value] of css.matchAll(/border-radius:\s*([^;]+);/g)) {
      expect(value.trim()).toBe("var(--radius-none)");
    }
    expect(css).not.toMatch(/var\(--radius-window\)/);
  });

  // "Never use drop-shadows on components (window only)." v2 spends its single shadow on the
  // terminal window; elevation otherwise reads from the seam between surface tiers.
  it.each(AUTHORED_CSS)("%s casts no shadow", (file) => {
    const css = declarations(file);
    expect(css).not.toMatch(/box-shadow:\s*(?!none)/);
    expect(css).not.toMatch(/var\(--shadow-/);
  });

  // "Never serif in product UI chrome, table cells, or buttons." Parastoo is display/marketing
  // only and this surface does not load it, so --f-display must not be reached for either.
  it.each(AUTHORED_CSS)("%s sets no serif face", (file) => {
    const css = declarations(file);
    expect(css).not.toMatch(/var\(--f-display\)/);
    expect(css).not.toMatch(/font-family:[^;]*\bserif\b/);
  });

  // The two families a product surface gets. A hand-written stack bypasses the system entirely and
  // is invisible to the colour gate — which is exactly how `Consolas, Monaco, "Andale Mono"…`
  // survived in two files under the previous system.
  it.each(AUTHORED_CSS)("%s names no font family outside the tokens", (file) => {
    const css = declarations(file);
    for (const [, value] of css.matchAll(/font-family:\s*([^;]+);/g)) {
      expect(value.trim()).toMatch(/^var\(--f-(sans|mono|wordmark)\)$/);
    }
  });

  // "Never gradients" — the one sanctioned gradient is --fusion-grad, on the leading leaderboard
  // row. Not a thing an admin console has.
  it.each(AUTHORED_CSS)("%s paints no gradient", (file) => {
    const css = declarations(file);
    expect(css).not.toMatch(/linear-gradient|radial-gradient|conic-gradient/);
    expect(css).not.toMatch(/var\(--fusion-grad/);
  });
});

describe("OME-709 · owner decisions that must survive a re-skin", () => {
  // "remove max-width please it's ugly" — full-bleed, explicitly.
  //
  // `max-width: 100%` is exempt and the distinction is real rather than a convenience: the owner
  // rejected CAPPING THE MEASURE — five ad-hoc column widths that made every block end somewhere
  // different. `max-width: 100%` on a replaced element caps nothing; it stops an oversized image
  // from overflowing its container, which is containment, the opposite of a cap. Anything with a
  // length or a viewport unit is the thing that was removed.
  it.each(AUTHORED_CSS)("%s reintroduces no width cap", (file) => {
    for (const [, value] of declarations(file).matchAll(/max-width:\s*([^;]+);/g)) {
      expect(value.trim()).toBe("100%");
    }
  });

  // The search button sits beside its input, not below it. `nowrap` plus a shrinkable basis is
  // what holds that: with `wrap` the button dropped to a second line whenever the two did not both
  // fit, which looked exactly like the original misalignment but had a different cause.
  it("keeps the search row on one line", () => {
    const css = read("app/globals.css");
    expect(css).toMatch(/\.accounts-search\s*\{[^}]*flex-wrap:\s*nowrap/);
    expect(css).toMatch(/\.accounts-search-field\s*\{[^}]*flex:\s*0 1 20rem/);
  });

  // A native <dialog> centres itself; the reset's `* { margin: 0 }` strips that and pins it to the
  // top-left. The SFDS reset does the same thing OMDS's did, so the fix has to be re-applied — it
  // is not inherited.
  it("restores margin:auto on the dialog the reset would strip", () => {
    expect(read("brand/tokens/base.css")).toMatch(/\*\s*\{\s*margin:\s*0;/);
    expect(read("app/globals.css")).toMatch(/\.tenant-dialog\s*\{[^}]*margin:\s*auto/);
  });
});

describe("the vendored token file", () => {
  const tokens = read("brand/tokens/tokens.css");

  // The whole divergence, and nothing beyond it: families resolve through next/font so the page
  // makes no request to a font CDN.
  it("routes every font family through a next/font variable", () => {
    for (const [, value] of tokens.matchAll(/^\s+(--f-[a-z]+:\s*[^;]+);/gm)) {
      expect(value).toMatch(/var\(--font-plex-(sans|mono)\)/);
    }
  });

  it("does not load Parastoo, which this surface may not use", () => {
    expect(tokens).not.toMatch(/"Parastoo"/);
  });

  // Proof the app register is the default rather than something we opted into: the marketing
  // override exists in the file, and nothing in the app turns it on.
  it("ships the marketing override unused", () => {
    expect(tokens).toMatch(/\[data-brand="marketing"\]/);
    for (const file of AUTHORED_CSS) {
      expect(declarations(file)).not.toMatch(/data-brand/);
    }
  });
});
