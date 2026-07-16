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
      <div className="flex min-h-0 flex-1 bg-sidebar">
        <AppSidebar />
        <SidebarInset
          aria-label="Workspace"
          className="h-full overflow-hidden rounded-tl-md"
        >
          {children}
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}
