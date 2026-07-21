import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";

import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center justify-center rounded-md px-1.5 py-0.5 text-xs font-medium whitespace-nowrap", {
  variants: { variant: { default: "bg-primary text-primary-foreground", secondary: "bg-muted text-muted-foreground", outline: "border border-border text-foreground" } },
  defaultVariants: { variant: "default" },
});

function Badge({ className, variant, asChild = false, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span";
  return <Comp className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
