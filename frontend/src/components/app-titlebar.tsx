"use client";

import { useEffect, useRef, useState } from "react";

import { TitlebarThemeToggle } from "@/components/theme-toggle";
import { SidebarTrigger, useSidebar } from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useIsTauri } from "@/hooks/use-is-tauri";

type TauriGlobal = {
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
        <div data-tauri-drag-region className="absolute left-1/2 -translate-x-1/2 text-xs font-semibold text-sidebar-foreground">ScreamingFace</div>
        <div className="pointer-events-auto"><TitlebarThemeToggle /></div>
      </div>
    </header>
  );
}
