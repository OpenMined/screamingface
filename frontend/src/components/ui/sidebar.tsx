"use client";

import * as React from "react";
import { Dialog, Slot } from "radix-ui";
import { PanelLeft, X } from "lucide-react";

import { useIsMobile } from "@/hooks/use-mobile";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

type SidebarContextValue = {
  state: "expanded" | "collapsed";
  isMobile: boolean;
  openMobile: boolean;
  setOpenMobile: (open: boolean) => void;
  toggleSidebar: () => void;
};

const SidebarContext = React.createContext<SidebarContextValue | null>(null);

function useSidebar() {
  const context = React.useContext(SidebarContext);
  if (!context) throw new Error("useSidebar must be used within SidebarProvider");
  return context;
}

function SidebarProvider({ defaultOpen = true, className, children, ...props }: React.ComponentProps<"div"> & { defaultOpen?: boolean }) {
  const isMobile = useIsMobile();
  const [open, setOpen] = React.useState(defaultOpen);
  const [openMobile, setOpenMobile] = React.useState(false);

  const toggleSidebar = React.useCallback(() => {
    if (isMobile) setOpenMobile((value) => !value);
    else setOpen((value) => !value);
  }, [isMobile]);

  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === "b" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        toggleSidebar();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleSidebar]);

  const value = React.useMemo(() => ({ state: open ? "expanded" as const : "collapsed" as const, isMobile, openMobile, setOpenMobile, toggleSidebar }), [open, isMobile, openMobile, toggleSidebar]);

  return (
    <SidebarContext.Provider value={value}>
      <TooltipProvider delayDuration={0}>
        <div className={cn("group/sidebar-wrapper flex min-h-svh w-full bg-background", className)} style={{ "--sidebar-width": "16rem", "--sidebar-width-icon": "3.5rem" } as React.CSSProperties} {...props}>
          {children}
        </div>
      </TooltipProvider>
    </SidebarContext.Provider>
  );
}

function Sidebar({ className, children, ...props }: React.ComponentProps<"aside">) {
  const { isMobile, openMobile, setOpenMobile, state } = useSidebar();

  if (isMobile) {
    return (
      <Dialog.Root open={openMobile} onOpenChange={setOpenMobile}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 data-[state=closed]:animate-out data-[state=open]:animate-in" />
          <Dialog.Content className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col bg-sidebar text-sidebar-foreground shadow-xl outline-none">
            <Dialog.Title className="sr-only">Primary navigation</Dialog.Title>
            <Dialog.Description className="sr-only">Navigate ScreamingFace and connect your OpenMined account.</Dialog.Description>
            {children}
            <Dialog.Close asChild><Button className="absolute right-2 top-2" size="icon" variant="ghost" aria-label="Close navigation"><X /></Button></Dialog.Close>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    );
  }

  return (
    <aside data-state={state} className={cn("group/sidebar relative hidden h-svh shrink-0 border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200 md:flex md:w-(--sidebar-width) md:data-[state=collapsed]:w-(--sidebar-width-icon)", className)} {...props}>
      <div className="flex size-full min-w-0 flex-col overflow-hidden">{children}</div>
    </aside>
  );
}

function SidebarHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex shrink-0 flex-col p-2", className)} {...props} />;
}

function SidebarContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex min-h-0 flex-1 flex-col overflow-auto", className)} {...props} />;
}

function SidebarFooter({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("flex shrink-0 flex-col p-2", className)} {...props} />;
}

function SidebarMenu({ className, ...props }: React.ComponentProps<"ul">) {
  return <ul className={cn("flex w-full min-w-0 flex-col gap-1", className)} {...props} />;
}

function SidebarMenuItem({ className, ...props }: React.ComponentProps<"li">) {
  return <li className={cn("group/menu-item relative", className)} {...props} />;
}

function SidebarMenuButton({ asChild = false, isActive = false, tooltip, className, ...props }: React.ComponentProps<"button"> & { asChild?: boolean; isActive?: boolean; tooltip?: string }) {
  const Comp = asChild ? Slot.Root : "button";
  const { state, isMobile } = useSidebar();
  const button = <Comp data-active={isActive} className={cn("flex h-9 w-full min-w-0 items-center gap-3 overflow-hidden rounded-md px-3 text-sm font-medium text-muted-foreground outline-none transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-sidebar-ring data-[active=true]:bg-sidebar-accent data-[active=true]:text-sidebar-accent-foreground group-data-[state=collapsed]/sidebar:size-10 group-data-[state=collapsed]/sidebar:justify-center group-data-[state=collapsed]/sidebar:px-0 group-data-[state=collapsed]/sidebar:[&>svg]:size-5 [&>span]:truncate [&>svg]:size-4 [&>svg]:shrink-0", className)} {...props} />;
  if (!tooltip) return button;
  return <Tooltip><TooltipTrigger asChild>{button}</TooltipTrigger><TooltipContent side="right" hidden={state !== "collapsed" || isMobile}>{tooltip}</TooltipContent></Tooltip>;
}

function SidebarTrigger({ className, ...props }: React.ComponentProps<typeof Button>) {
  const { toggleSidebar } = useSidebar();
  return <Button {...props} variant="ghost" size="icon" className={cn("size-8", className)} onClick={(event) => { props.onClick?.(event); toggleSidebar(); }}><PanelLeft /><span className="sr-only">Toggle sidebar</span></Button>;
}

function SidebarRail({ className, ...props }: React.ComponentProps<"button">) {
  const { toggleSidebar } = useSidebar();
  return <button aria-label="Toggle sidebar" tabIndex={-1} onClick={toggleSidebar} className={cn("absolute inset-y-0 -right-2 z-20 hidden w-4 cursor-col-resize md:block after:absolute after:inset-y-0 after:left-1/2 after:w-px hover:after:bg-sidebar-border", className)} {...props} />;
}

function SidebarInset({ className, ...props }: React.ComponentProps<"main">) {
  return <main className={cn("relative flex min-w-0 flex-1 flex-col bg-background", className)} {...props} />;
}

export { Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarInset, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarProvider, SidebarRail, SidebarTrigger, useSidebar };
