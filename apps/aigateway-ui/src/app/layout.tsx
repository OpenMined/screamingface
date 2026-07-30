import type { Metadata } from "next";
import { Inter, Rubik } from "next/font/google";

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
    <html lang="en" className={`${inter.variable} ${rubik.variable}`}>
      <body>{children}</body>
    </html>
  );
}
