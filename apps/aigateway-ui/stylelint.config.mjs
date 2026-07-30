/**
 * OMDS enforcement gate — adapted from OpenMined/brand.openmined.org.
 *
 * Raw color values are un-shippable. `src/brand/tokens/tokens.css` is the single place literal
 * palette values may live; every other file must reference a token via var(--…).
 *
 * Three rules, deliberately minimal — a focused gate stays high-signal for both humans and
 * agents. Upstream does NOT extend stylelint-config-standard on purpose: its ~40 stylistic rules
 * would bury the one rule that matters under noise. Kept that way here.
 *
 * Divergence from upstream: no `postcss-html` override for `.astro` files (this is a React app,
 * so styles live in .css and CSS Modules), and the ignore list points at the vendored token path
 * rather than upstream's `src/tokens/`.
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

export default {
  ignoreFiles: [
    ".next/**",
    "coverage/**",
    "node_modules/**",
    // The palette IS the raw-value source of truth — literal hex is correct here. Vendored
    // verbatim from upstream, which exempts the same file for the same reason.
    "src/brand/tokens/tokens.css",
  ],

  plugins: ["stylelint-declaration-strict-value"],

  rules: {
    "color-no-hex": [
      true,
      {
        message:
          "OMDS: no raw hex. Use a token — e.g. var(--color-teal-600), var(--surface-background-default), var(--text-body). Literal palette values live only in src/brand/tokens/tokens.css.",
      },
    ],

    "color-named": [
      "never",
      {
        message: "OMDS: no named colors. Use a design token via var(--…).",
      },
    ],

    "scale-unlimited/declaration-strict-value": [
      COLOR_PROPS,
      {
        ignoreKeywords: ALLOWED_KEYWORDS,
        ignoreFunctions: false, // disallow rgb()/hsl() literals — only var() passes
        disableFix: true,
        message:
          "OMDS: color properties must reference a design token — use var(--…) from tokens.css, not a literal value.",
      },
    ],
  },
};
