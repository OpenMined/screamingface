import type { Metadata } from "next";
import { ThemeProvider } from "@/components/theme-provider";
import { NativeThemeSync } from "@/components/native-theme-sync";
import "./globals.css";

export const metadata: Metadata = {
  title: "ScreamingFace",
  description: "The loudest fusion hub",
  icons: {
    icon: "/icon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-full">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <NativeThemeSync />
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
