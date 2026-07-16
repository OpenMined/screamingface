import { AppSidebar } from "@/components/app-sidebar";
import { AppTitlebar } from "@/components/app-titlebar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

export default function StudioLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <SidebarProvider className="h-svh min-h-0 flex-col overflow-hidden">
      <AppTitlebar />
      <div className="flex min-h-0 flex-1 overflow-hidden bg-sidebar">
        <AppSidebar />
        <SidebarInset
          aria-label="Workspace"
          className="mx-2 mb-2 min-h-0 flex-1 overflow-hidden rounded-md border border-sidebar-border"
        >
          {children}
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}
