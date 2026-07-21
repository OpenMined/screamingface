"use client";

import { useEffect, useRef, useState } from "react";
import { Download } from "lucide-react";

import { TitlebarThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { SidebarTrigger, useSidebar } from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useIsTauri } from "@/hooks/use-is-tauri";

type TauriGlobal = {
  core?: { invoke?: (command: string) => Promise<unknown> };
  event?: { listen?: (event: string, handler: () => void) => Promise<() => void> };
  window?: { getCurrentWindow?: () => { isFullscreen?: () => Promise<boolean> } };
};

export function AppTitlebar() {
  const isTauri = useIsTauri();
  const { state } = useSidebar();
  const titlebarRef = useRef<HTMLElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const isMac = typeof navigator !== "undefined" && navigator.platform.toLowerCase().includes("mac");
  const sidebarAction = state === "collapsed" ? "Expand sidebar" : "Collapse sidebar";
  const checkForUpdates = () => {
    const tauri = (window as Window & { __TAURI__?: TauriGlobal }).__TAURI__;
    void tauri?.core?.invoke?.("check_for_updates");
  };

  useEffect(() => {
    if (!isTauri) return;
    const tauri = (window as Window & { __TAURI__?: TauriGlobal }).__TAURI__;
    let unlisten: (() => void) | undefined;

    const refreshFullscreen = async () => {
      const fullscreen = await tauri?.window?.getCurrentWindow?.().isFullscreen?.();
      setIsFullscreen(Boolean(fullscreen));
    };
    const removeDuplicateTitlebars = () => {
      document.querySelectorAll<HTMLElement>("[data-tauri-decorum-tb]").forEach((element) => {
        if (element !== titlebarRef.current) element.remove();
      });
    };

    const timer = window.setTimeout(removeDuplicateTitlebars, 0);
    void refreshFullscreen();
    void tauri?.event?.listen?.("tauri://resize", refreshFullscreen).then((cleanup) => { unlisten = cleanup; });
    return () => {
      window.clearTimeout(timer);
      unlisten?.();
    };
  }, [isTauri]);

  if (!isTauri) return null;

  return (
    <header ref={titlebarRef} data-tauri-decorum-tb="" className="relative flex h-10 w-full shrink-0 select-none items-center bg-sidebar px-4 text-sidebar-foreground">
      <div data-tauri-drag-region className={isMac && !isFullscreen ? "absolute inset-y-0 left-20 right-0 z-0" : "absolute inset-0 z-0"} />
      <div className="pointer-events-none relative z-10 flex w-full items-center justify-between">
        <div className={isMac && !isFullscreen ? "pointer-events-auto pl-16" : "pointer-events-auto"}>
          <Tooltip>
            <TooltipTrigger asChild>
              <SidebarTrigger
                aria-label={sidebarAction}
                className="hover:bg-sidebar-accent hover:text-foreground [&_svg]:size-4"
              />
            </TooltipTrigger>
            <TooltipContent side="bottom">{sidebarAction}</TooltipContent>
          </Tooltip>
        </div>
        <div className="pointer-events-auto flex items-center gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="group h-8 gap-1.5 px-2 text-muted-foreground hover:bg-sidebar-accent hover:px-2.5 hover:text-foreground focus-visible:px-2.5"
                aria-label="Check for updates"
                onClick={checkForUpdates}
              >
                <Download className="size-4" />
                <span className="hidden group-hover:inline group-focus-visible:inline">
                  Check for update
                </span>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Check for updates</TooltipContent>
          </Tooltip>
          <TitlebarThemeToggle />
        </div>
      </div>
    </header>
  );
}
