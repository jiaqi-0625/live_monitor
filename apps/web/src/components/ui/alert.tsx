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
        "relative w-full rounded-lg border bg-card px-4 py-3 text-sm",
        className,
      )}
      {...props}
    />
  )
}

