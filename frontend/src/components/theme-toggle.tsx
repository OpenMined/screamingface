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

export function ThemeToggle() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  const { state: sidebarState, isMobile } = useSidebar();
  const preference = theme ? theme[0].toUpperCase() + theme.slice(1) : "System";
  const appearance = resolvedTheme ? resolvedTheme[0].toUpperCase() + resolvedTheme.slice(1) : undefined;
  const tooltip = theme === "system" && appearance ? `Theme: ${preference} (${appearance})` : `Theme: ${preference}`;

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
        <TooltipContent side="right" hidden={sidebarState !== "collapsed" || isMobile}>{tooltip}</TooltipContent>
      </Tooltip>
      <DropdownMenuContent side="right" align="end">
        <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
          {themes.map(({ value, label, Icon }) => <DropdownMenuRadioItem value={value} key={value}><Icon />{label}</DropdownMenuRadioItem>)}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
