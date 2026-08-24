import { cva, type VariantProps } from "class-variance-authority"
import type { HTMLAttributes } from "react"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium leading-none ring-1 ring-inset ring-transparent",
  {
    variants: {
      variant: {
        default: "bg-primary/10 text-primary ring-primary/10",
        secondary: "bg-secondary text-secondary-foreground ring-border/50",
        outline: "bg-card text-foreground ring-border",
        success: "bg-success/12 text-success ring-success/15",
        warning: "bg-warning/16 text-warning-foreground ring-warning/20",
        destructive: "bg-destructive/10 text-destructive ring-destructive/15",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
)

export function Badge({
  className,
  variant,
  ...props
}: HTMLAttributes<HTMLSpanElement> &
  VariantProps<typeof badgeVariants>) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

