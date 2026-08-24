import type { HTMLAttributes } from "react"

import { cn } from "@/lib/utils"

export function Alert({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="alert"
      className={cn(
        "relative w-full rounded-xl border border-border/80 bg-card px-4 py-3.5 text-sm leading-6 shadow-[0_1px_2px_hsl(var(--shadow-color)/0.025)]",
        className,
      )}
      {...props}
    />
  )
}

