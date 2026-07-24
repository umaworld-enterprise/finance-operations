"use client";

import * as React from "react";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface HelpTooltipProps {
  content: string;
  className?: string;
}

export function HelpTooltip({ content, className }: HelpTooltipProps) {
  return (
    <PopoverPrimitive.Root>
      <PopoverPrimitive.Trigger asChild>
        <button
          type="button"
          aria-label="More information"
          className={cn(
            "inline-flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-full",
            className
          )}
        >
          <HelpCircle className="h-4 w-4" />
        </button>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          sideOffset={6}
          side="top"
          align="center"
          className={cn(
            "z-50 w-72 rounded-lg border border-border bg-popover p-3 text-xs text-popover-foreground shadow-md",
            "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
          )}
        >
          {content}
          <PopoverPrimitive.Arrow className="fill-popover" />
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
