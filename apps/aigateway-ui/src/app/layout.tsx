import type { Metadata } from "next";
import { Inter, Rubik } from "next/font/google";

import { ThemeSwitch } from "./theme";

import "./globals.css";

// OMDS pairs Rubik (headings) with Inter (body). next/font self-hosts both at build time, so the
// rendered page makes no request to a font CDN — upstream's typography.css carries a TODO to do
// exactly that "before production". It matters here specifically: this console is internal tooling
// behind Cloudflare Access, and a third-party request from an admin page is both a leak and a
// failure mode.
//
// The vendored token files reference these as var(--font-inter) / var(--font-rubik) rather than
// the literal family names upstream hardcodes — the one documented divergence, see
// src/brand/README.md.
const inter = Inter({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-inter",
});

const rubik = Rubik({
  subsets: ["latin"],
  weight: ["400"],
  variable: "--font-rubik",
});

export const metadata: Metadata = {
  title: "aigateway admin",
  description: "Manage gateway accounts and their provider API keys.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // `suppressHydrationWarning` because the served script below sets `data-theme` on this element
    // before React hydrates, so the client DOM legitimately differs from the server markup. Scoped
    // to <html> only — it does not mask a mismatch anywhere else.
    <html lang="en" className={`${inter.variable} ${rubik.variable}`} suppressHydrationWarning>
      <head>
        {/*
          Applies the stored theme BEFORE first paint. A React effect runs after paint, so the page
          would render light and then flip — a visible flash on load and on every navigation.

          A served same-origin file rather than an inline script: the document then contains no
          injected HTML at all, and a future Content-Security-Policy needs no 'unsafe-inline'.
          Parser-blocking by design — no `async`/`defer` — because running late is the whole bug.
          Kept in step with `applyStoredTheme` by theme.test.tsx.
        */}
        {/* eslint-disable-next-line @next/next/no-sync-scripts --
            The rule guards against render-blocking scripts, and blocking is the entire point here:
            a deferred or async script runs after first paint, which is the flash this exists to
            prevent. The cost is one same-origin request for ~400 bytes, cached after first load. */}
        <script src="/theme-init.js" />
      </head>
      <body>
        <header className="app-bar">
          <span className="app-bar-mark">aigateway admin</span>
          <ThemeSwitch />
        </header>
        {children}
      </body>
    </html>
  );
}
