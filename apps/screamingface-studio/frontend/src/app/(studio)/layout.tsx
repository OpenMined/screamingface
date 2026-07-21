"use client";

import { AppSidebar } from "@/components/app-sidebar";
import { AppTitlebar } from "@/components/app-titlebar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { useIsTauri } from "@/hooks/use-is-tauri";
import { cn } from "@/lib/utils";

export default function StudioLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const isTauri = useIsTauri();

  return (
    <SidebarProvider className="h-svh min-h-0 flex-col overflow-hidden">
      <AppTitlebar />
      <div className="flex min-h-0 flex-1 overflow-hidden bg-sidebar">
        <AppSidebar />
        <SidebarInset
          aria-label="Workspace"
          className={cn(
            "mx-2 mb-2 min-h-0 flex-1 overflow-hidden rounded-md border border-sidebar-border",
            isTauri === false && "mt-2",
          )}
        >
          {children}
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}
