"use client";

import { Tooltip as TooltipPrimitive } from "radix-ui";
import { cn } from "@/lib/utils";

const TooltipProvider = TooltipPrimitive.Provider;
const Tooltip = TooltipPrimitive.Root;
const TooltipTrigger = TooltipPrimitive.Trigger;

function TooltipContent({ className, sideOffset = 4, ...props }: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content sideOffset={sideOffset} className={cn("z-50 rounded-md bg-foreground px-2.5 py-1.5 text-xs text-background shadow-md", className)} {...props} />
    </TooltipPrimitive.Portal>
  );
}

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger };
