"use client";

import { Check } from "lucide-react";
import { DropdownMenu as DropdownMenuPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

const DropdownMenu = DropdownMenuPrimitive.Root;
const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger;

function DropdownMenuContent({ className, sideOffset = 6, ...props }: React.ComponentProps<typeof DropdownMenuPrimitive.Content>) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content sideOffset={sideOffset} className={cn("z-50 min-w-40 rounded-xl border bg-popover p-1.5 text-popover-foreground shadow-xl outline-none", className)} {...props} />
    </DropdownMenuPrimitive.Portal>
  );
}

function DropdownMenuRadioGroup(props: React.ComponentProps<typeof DropdownMenuPrimitive.RadioGroup>) {
  return <DropdownMenuPrimitive.RadioGroup {...props} />;
}

function DropdownMenuRadioItem({ className, children, ...props }: React.ComponentProps<typeof DropdownMenuPrimitive.RadioItem>) {
  return (
    <DropdownMenuPrimitive.RadioItem className={cn("relative flex cursor-default select-none items-center gap-2 rounded-lg py-2 pl-2 pr-8 text-sm outline-none transition-colors focus:bg-secondary data-[disabled]:pointer-events-none data-[disabled]:opacity-50 [&_svg]:size-4", className)} {...props}>
      {children}
      <span className="absolute right-2 flex size-4 items-center justify-center"><DropdownMenuPrimitive.ItemIndicator><Check className="size-4" /></DropdownMenuPrimitive.ItemIndicator></span>
    </DropdownMenuPrimitive.RadioItem>
  );
}

export { DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger };
