"use client";

import { Popover as PopoverPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

const Popover = PopoverPrimitive.Root;
const PopoverTrigger = PopoverPrimitive.Trigger;

function PopoverContent({ className, align = "center", sideOffset = 8, ...props }: React.ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        align={align}
        sideOffset={sideOffset}
        className={cn("z-50 w-72 rounded-2xl border bg-popover p-1 text-popover-foreground shadow-xl outline-none data-[state=closed]:animate-out data-[state=open]:animate-in", className)}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
}

export { Popover, PopoverContent, PopoverTrigger };
