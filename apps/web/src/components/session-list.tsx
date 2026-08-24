import {
  CircleStop,
  Clock3,
  Radio,
  RadioTower,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn, formatDateTime, formatDuration } from "@/lib/utils"
import type { LiveSession } from "@/types"

const platformNames = {
  douyin: "抖音",
  dongchedi: "懂车云店",
}

const statusConfig = {
  created: { label: "等待采集", variant: "warning" as const },
  live: { label: "监控中", variant: "success" as const },
  ended: { label: "已结束", variant: "secondary" as const },
  failed: { label: "异常", variant: "destructive" as const },
}

interface SessionListProps {
  sessions: LiveSession[]
  activeId: string | null
  loading: boolean
  onSelect: (sessionId: string) => void
}

export function SessionList({
  sessions,
  activeId,
  loading,
  onSelect,
}: SessionListProps) {
  if (loading) {
    return (
      <div className="grid gap-2 px-3" aria-label="正在加载场次">
        {[0, 1, 2].map((item) => (
          <div
            key={item}
            className="h-20 animate-pulse rounded-xl bg-sidebar-accent"
          />
        ))}
      </div>
    )
  }

  if (sessions.length === 0) {
    return (
      <div className="mx-3 rounded-xl border border-sidebar-border bg-sidebar-accent/35 px-3 py-6 text-center">
        <RadioTower className="mx-auto mb-2 size-5 text-sidebar-muted" />
        <p className="text-sm font-medium">暂无场次</p>
        <p className="mt-1 text-xs text-sidebar-muted">
          从右侧创建第一场监控。
        </p>
      </div>
    )
  }

  return (
    <div className="grid gap-1.5 px-2">
      {sessions.map((session) => {
        const config = statusConfig[session.status]
        return (
          <button
            key={session.id}
            type="button"
            onClick={() => onSelect(session.id)}
            className={cn(
              "group relative grid w-full gap-2 overflow-hidden rounded-xl px-3 py-3 text-left text-sidebar-foreground outline-none transition-colors before:absolute before:bottom-3 before:left-0 before:top-3 before:w-0.5 before:rounded-full before:bg-primary before:opacity-0 hover:bg-sidebar-accent/75 focus-visible:ring-2 focus-visible:ring-ring",
              activeId === session.id && "bg-sidebar-accent before:opacity-100 ring-1 ring-inset ring-sidebar-border",
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-sm font-medium">
                {session.title}
              </span>
              <Badge variant={config.variant}>{config.label}</Badge>
            </div>
            <div className="flex items-center gap-3 text-xs text-sidebar-muted">
              <span className="flex items-center gap-1">
                {session.status === "live" ? (
                  <Radio className="size-3" />
                ) : (
                  <CircleStop className="size-3" />
                )}
                {platformNames[session.platform]}
              </span>
              <span className="flex items-center gap-1 tabular-nums">
                <Clock3 className="size-3" />
                {formatDuration(session.duration_seconds)}
              </span>
            </div>
            <span className="text-[11px] text-sidebar-muted">
              {formatDateTime(session.created_at)}
            </span>
          </button>
        )
      })}
    </div>
  )
}

