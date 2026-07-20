"use client";

import { Boxes, FileCode, Flame, Hash, Key, Layers, Plug, Sparkles, Trophy, User } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { SidebarThemeToggle } from "@/components/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarRail } from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useIsTauri } from "@/hooks/use-is-tauri";
import { useEnsembleStore } from "@/lib/ensemble-store";
import { useModelStore } from "@/lib/model-store";

const navigation = [
  { label: "Ensembles", href: "/ensembles/", Icon: Boxes },
  { label: "Models", href: "/models/", Icon: Layers },
  { label: "Leaderboard", href: "/leaderboard/", Icon: Trophy },
  { label: "Scripts", href: "/scripts/", Icon: FileCode, badge: "2" },
];

function MonsterFusionCard() {
  return (
    <section className="flex flex-col gap-2.5 rounded-2xl border border-primary/20 bg-gradient-to-br from-primary/12 to-primary/[0.04] p-3.5 shadow-sm">
      <div className="flex items-center gap-2 text-xs font-medium text-primary"><Flame className="size-3.5" /><span>Monster Fusion Program</span></div>
      <p className="text-[11px] leading-relaxed text-muted-foreground">Connect your key to use subsidized OpenMined compute.</p>
      <div className="relative">
        <Key className="absolute left-2.5 top-1/2 z-10 size-3 -translate-y-1/2 text-muted-foreground" />
        <Input type="password" placeholder="om-…" aria-label="OpenMined key" className="h-8 pl-8 font-mono text-xs" />
      </div>
      <Button size="sm" type="button"><Plug className="size-3.5" />Connect OpenMined</Button>
      <Button size="sm" variant="outline" asChild><a href="https://openmined.org" target="_blank" rel="noreferrer"><Sparkles className="size-3.5" />Apply</a></Button>
    </section>
  );
}

export function AppSidebar() {
  const pathname = usePathname();
  const isTauri = useIsTauri();
  const ensembles = useEnsembleStore((state) => state.ensembles);
  const activeEnsembleId = useEnsembleStore(
    (state) => state.activeEnsembleId,
  );
  const connectedProviders = useModelStore(
    (state) =>
      state.providers.filter((provider) => provider.connected).length,
  );

  return (
    <Sidebar aria-label="Primary navigation">
      <SidebarHeader className="border-b border-sidebar-border bg-sidebar p-3 group-data-[state=collapsed]/sidebar:p-2">
        <div className="flex h-10 items-center gap-2">
          <Link href="/" className="group/brand flex min-w-0 flex-1 items-center gap-2.5 overflow-hidden rounded-md px-1 group-data-[state=collapsed]/sidebar:justify-center group-data-[state=collapsed]/sidebar:px-0">
            <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-primary/15 text-base shadow-sm ring-1 ring-primary/10 transition-transform group-hover/brand:rotate-[8deg]" aria-hidden="true">😱</span>
            <span className="min-w-0 group-data-[state=collapsed]/sidebar:hidden">
              <span className="block truncate text-sm font-semibold">ScreamingFace</span>
              <span className="block truncate font-mono text-[10px] text-muted-foreground">the loudest ensemble hub</span>
            </span>
          </Link>
        </div>
      </SidebarHeader>

      <SidebarContent className="overflow-hidden p-3 group-data-[state=collapsed]/sidebar:p-2">
        <nav aria-label="Studio" className="shrink-0">
          <SidebarMenu>
            {navigation.map(({ label, href, Icon, badge }) => {
              const visibleBadge =
                label === "Models" && connectedProviders > 0
                  ? String(connectedProviders)
                  : badge;
              return (
                <SidebarMenuItem key={label}>
                  <SidebarMenuButton
                    asChild
                    isActive={pathname.startsWith(href)}
                    tooltip={label}
                    className="hover:bg-sidebar-accent/40 data-[active=true]:bg-sidebar-accent data-[active=true]:hover:bg-sidebar-accent"
                  >
                    <Link href={href} prefetch={false}>
                      <Icon />
                      <span className="group-data-[state=collapsed]/sidebar:hidden">
                        {label}
                      </span>
                      {visibleBadge && (
                        <Badge
                          variant="secondary"
                          className="ml-auto font-mono text-xs group-data-[state=collapsed]/sidebar:hidden"
                        >
                          {visibleBadge}
                        </Badge>
                      )}
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </nav>

        {ensembles.length > 0 && (
          <nav
            aria-label="My ensembles"
            className="mt-5 flex min-h-0 flex-1 flex-col group-data-[state=collapsed]/sidebar:hidden"
          >
            <p className="mb-2 shrink-0 px-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              My Ensembles
            </p>
            <SidebarMenu className="min-h-0 overflow-y-auto">
              {ensembles.map((ensemble) => (
                <SidebarMenuItem key={ensemble.id}>
                  <SidebarMenuButton
                    asChild
                    isActive={
                      pathname === "/ensembles/new/" &&
                      activeEnsembleId === ensemble.id
                    }
                    className="hover:bg-sidebar-accent/40 data-[active=true]:bg-sidebar-accent/60"
                  >
                    <Link
                      href={`/ensembles/new/?id=${encodeURIComponent(ensemble.id)}`}
                      prefetch={false}
                    >
                      <Hash className="size-3" />
                      <span className="truncate font-mono text-xs">
                        {ensemble.name}
                      </span>
                      {ensemble.runs > 0 && (
                        <span className="ml-auto font-mono text-xs text-muted-foreground">
                          {ensemble.runs}
                        </span>
                      )}
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </nav>
        )}
      </SidebarContent>

      <SidebarFooter className="gap-3 border-t border-sidebar-border p-3 group-data-[state=collapsed]/sidebar:p-2">
        <div className="max-h-96 origin-bottom overflow-hidden opacity-100 scale-100 translate-y-0 transition-[max-height,opacity,transform] duration-200 delay-150 ease-out group-data-[state=collapsed]/sidebar:invisible group-data-[state=collapsed]/sidebar:max-h-0 group-data-[state=collapsed]/sidebar:translate-y-2 group-data-[state=collapsed]/sidebar:scale-75 group-data-[state=collapsed]/sidebar:opacity-0 group-data-[state=collapsed]/sidebar:delay-0 group-data-[state=collapsed]/sidebar:ease-in">
          <MonsterFusionCard />
        </div>

        <div className="flex max-h-0 origin-center scale-75 justify-center overflow-hidden opacity-0 transition-[max-height,opacity,transform] duration-150 ease-in pointer-events-none group-data-[state=collapsed]/sidebar:max-h-10 group-data-[state=collapsed]/sidebar:scale-100 group-data-[state=collapsed]/sidebar:opacity-100 group-data-[state=collapsed]/sidebar:delay-100 group-data-[state=collapsed]/sidebar:ease-out group-data-[state=collapsed]/sidebar:pointer-events-auto">
          <Popover>
            <Tooltip>
              <TooltipTrigger asChild>
                <PopoverTrigger asChild>
                  <Button variant="ghost" size="icon" className="size-10 text-primary hover:bg-primary/10 hover:text-primary" aria-label="Monster Fusion Program">
                    <Flame className="size-5" />
                  </Button>
                </PopoverTrigger>
              </TooltipTrigger>
              <TooltipContent side="right">Monster Fusion Program</TooltipContent>
            </Tooltip>
            <PopoverContent side="right" align="end" className="border-0 bg-transparent p-0 shadow-none">
              <MonsterFusionCard />
            </PopoverContent>
          </Popover>
        </div>

        {isTauri === false && <SidebarThemeToggle />}

        <div className="flex h-10 items-center gap-2.5 overflow-hidden rounded-md px-1 group-data-[state=collapsed]/sidebar:justify-center group-data-[state=collapsed]/sidebar:px-0">
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary/15 text-primary transition-[width,height] duration-200 group-data-[state=collapsed]/sidebar:size-10"><User className="size-4 transition-[width,height] duration-200 group-data-[state=collapsed]/sidebar:size-5" /></span>
          <span className="min-w-0 group-data-[state=collapsed]/sidebar:hidden"><strong className="block truncate text-sm font-normal">irina</strong><small className="block truncate font-mono text-[10px] text-muted-foreground">irina@openmined.org</small></span>
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
