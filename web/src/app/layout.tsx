import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "😱 screamingface — the real cost of intelligence",
  description:
    "How much does it cost to solve a problem with AI? Live cost-per-accuracy data across models and tasks. Open data, open methodology.",
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
      <body>{children}</body>
    </html>
  );
}
