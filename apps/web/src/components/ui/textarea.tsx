import type { TextareaHTMLAttributes } from "react"

import { cn } from "@/lib/utils"

export function Textarea({
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "flex min-h-28 w-full resize-y rounded-lg border border-input bg-card px-3 py-2.5 text-sm leading-6 shadow-[0_1px_2px_hsl(var(--shadow-color)/0.025)] outline-none transition-[border-color,box-shadow] placeholder:text-muted-foreground/75 focus-visible:border-primary/50 focus-visible:ring-3 focus-visible:ring-ring/15 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  )
}
