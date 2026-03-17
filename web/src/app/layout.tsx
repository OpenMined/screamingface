import type { Metadata } from "next";
import PasswordGate from "@/components/PasswordGate";
import "./globals.css";

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
    <html lang="en">
      <body className="antialiased bg-background text-foreground">
        <PasswordGate>{children}</PasswordGate>
      </body>
    </html>
  );
}
