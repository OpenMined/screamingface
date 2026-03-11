import type { Metadata } from "next";
import { Inter, Rubik, Sometype_Mono } from "next/font/google";
import PasswordGate from "@/components/PasswordGate";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const rubik = Rubik({
  variable: "--font-rubik",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const sotypeMono = Sometype_Mono({
  variable: "--font-sometype-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "screamingface — SOTA on your laptop",
  description:
    "An AI ensemble that combines Claude Code, Gemini CLI, Codex, and Ollama to beat state-of-the-art benchmarks. One command to install.",
  robots: {
    index: false,
    follow: false,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${inter.variable} ${rubik.variable} ${sotypeMono.variable} antialiased bg-background text-foreground`}
      >
        <PasswordGate>{children}</PasswordGate>
      </body>
    </html>
  );
}
