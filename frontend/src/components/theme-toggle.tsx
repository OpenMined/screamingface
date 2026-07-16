"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useSidebar } from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const themes = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "System", Icon: Monitor },
];

function useThemeControl() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const preference = theme ? theme[0].toUpperCase() + theme.slice(1) : "System";
  const appearance = resolvedTheme ? resolvedTheme[0].toUpperCase() + resolvedTheme.slice(1) : undefined;
  const tooltip = theme === "system" && appearance ? `Theme: ${preference} (${appearance})` : `Theme: ${preference}`;
  return { theme, setTheme, tooltip };
}

function ThemeOptions({ theme, setTheme }: { theme?: string; setTheme: (theme: string) => void }) {
  return (
    <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
      {themes.map(({ value, label, Icon }) => <DropdownMenuRadioItem value={value} key={value}><Icon />{label}</DropdownMenuRadioItem>)}
    </DropdownMenuRadioGroup>
  );
}

export function SidebarThemeToggle() {
  const { theme, setTheme, tooltip } = useThemeControl();
  const { state, isMobile } = useSidebar();

  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-10 w-full justify-start gap-3 px-2 text-muted-foreground hover:text-foreground group-data-[state=collapsed]/sidebar:size-10 group-data-[state=collapsed]/sidebar:justify-center group-data-[state=collapsed]/sidebar:px-0" aria-label="Choose color theme">
              <Sun className="size-4 dark:hidden group-data-[state=collapsed]/sidebar:size-5" />
              <Moon className="hidden size-4 dark:block group-data-[state=collapsed]/sidebar:size-5" />
              <span className="text-sm font-medium group-data-[state=collapsed]/sidebar:hidden">Theme</span>
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="right" hidden={state !== "collapsed" || isMobile}>{tooltip}</TooltipContent>
      </Tooltip>
      <DropdownMenuContent side="right" align="end">
        <ThemeOptions theme={theme} setTheme={setTheme} />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function TitlebarThemeToggle() {
  const { theme, setTheme, tooltip } = useThemeControl();

  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="relative size-8 text-muted-foreground hover:bg-sidebar-accent hover:text-foreground" aria-label="Choose color theme">
              <Sun className="size-4 dark:hidden" />
              <Moon className="hidden size-4 dark:block" />
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom">{tooltip}</TooltipContent>
      </Tooltip>
      <DropdownMenuContent side="bottom" align="end" sideOffset={8}>
        <ThemeOptions theme={theme} setTheme={setTheme} />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
