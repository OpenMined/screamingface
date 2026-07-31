/**
 * SFDS enforcement gate — the ScreamingFace Design System v2 (OME-716).
 *
 * Raw color values are un-shippable. `src/brand/tokens/tokens.css` is the single place literal
 * palette values may live; every other file must reference a token via var(--…).
 *
 * The rules are deliberately minimal — a focused gate stays high-signal for both humans and
 * agents. Extending stylelint-config-standard would bury the one rule that matters under ~40
 * stylistic complaints.
 *
 * This gate is system-independent: it survived the OMDS → SFDS migration unchanged except for the
 * message text, because "literal colors don't ship" is a property of the discipline, not of the
 * palette. It has already caught one real hole (see `function-disallowed-list` below).
 */

// `/color$/` matches color, background-color, border-*-color, outline-color, caret-color,
// text-decoration-color, column-rule-color — but NOT color-scheme.
//
// box-shadow is intentionally absent: the 1px-ring hack (`box-shadow: 0 0 0 1px var(--token)`)
// tokenizes the color but cannot be a single var(), so it would false-positive. color-no-hex and
// color-named still police shadow colors.
const COLOR_PROPS = ["/color$/", "fill", "stroke"];

// Bare CSS-wide keywords that are legal on color properties and carry no value.
const ALLOWED_KEYWORDS = [
  "currentColor",
  "transparent",
  "inherit",
  "initial",
  "unset",
  "revert",
  "none",
];

const config = {
  ignoreFiles: [
    ".next/**",
    "coverage/**",
    "node_modules/**",
    // The palette IS the raw-value source of truth — literal hex is correct here. Vendored
    // from brand.screamingface.ai, verbatim apart from one documented font divergence.
    "src/brand/tokens/tokens.css",
  ],

  plugins: ["stylelint-declaration-strict-value"],

  rules: {
    "color-no-hex": [
      true,
      {
        message:
          "SFDS: no raw hex. Use a semantic token — e.g. var(--accent-solid), var(--surface), var(--text-2). Literal palette values live only in src/brand/tokens/tokens.css.",
      },
    ],

    "color-named": [
      "never",
      {
        message: "SFDS: no named colors. Use a design token via var(--…).",
      },
    ],

    // Closes a hole the OME-708 review PROVED, not inferred. `declaration-strict-value` is scoped
    // to color-ish properties, and `color-no-hex`/`color-named` only see hex and names — so a
    // functional literal on a SHORTHAND slipped through every check:
    //     outline: 2px solid rgb(56 140 168);
    //     border-left: 4px solid hsl(200 50% 40%);
    //     box-shadow: 0 0 0 2px rgb(...);
    // which is exactly the form every focus ring in this app is written in. Widening COLOR_PROPS
    // instead would false-positive on `border: 1px solid var(--x)`, so the ban is on the functions.
    "function-disallowed-list": [
      ["rgb", "rgba", "hsl", "hsla", "hwb", "lab", "lch", "oklab", "oklch", "color"],
      {
        message:
          "SFDS: no functional color literals. Use var(--…) from tokens.css — a shorthand like `border: 1px solid rgb(…)` evades the other rules.",
      },
    ],

    "scale-unlimited/declaration-strict-value": [
      COLOR_PROPS,
      {
        ignoreKeywords: ALLOWED_KEYWORDS,
        ignoreFunctions: false, // disallow rgb()/hsl() literals — only var() passes
        disableFix: true,
        message:
          "SFDS: color properties must reference a design token — use var(--…) from tokens.css, not a literal value.",
      },
    ],
  },
};

export default config;
