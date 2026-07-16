import { AppSidebar } from "@/components/app-sidebar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

export default function StudioLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset aria-label="Workspace" className="h-svh overflow-hidden">
        {children}
      </SidebarInset>
    </SidebarProvider>
  );
}
