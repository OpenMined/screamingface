import { AppSidebar } from "@/components/app-sidebar";

export default function StudioLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="app-shell">
      <AppSidebar />
      <main className="workspace" aria-label="Workspace">
        {children}
      </main>
    </div>
  );
}
