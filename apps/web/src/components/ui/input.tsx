import type { InputHTMLAttributes } from "react"

import { cn } from "@/lib/utils"

export function Input({
  className,
  type,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-lg border border-input bg-card px-3 py-1 text-sm shadow-[0_1px_2px_hsl(var(--shadow-color)/0.025)] outline-none transition-[border-color,box-shadow] placeholder:text-muted-foreground/75 focus-visible:border-primary/50 focus-visible:ring-3 focus-visible:ring-ring/15 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  )
}

