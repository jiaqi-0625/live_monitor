import { useCallback, useEffect, useMemo, useState } from "react"
import {
  Activity,
  ArrowRight,
  Clock3,
  Radio,
  RefreshCw,
  Target,
  UsersRound,
} from "lucide-react"

import { Alert } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { getMultiRoomOverview } from "@/lib/api"
import { formatDateTime, formatDuration } from "@/lib/utils"
import type { LiveRoomOverview, MultiRoomOverview } from "@/types"

interface MultiRoomOverviewProps {
  operatorName: string
  onCreate: () => void
  onSelect: (sessionId: string) => void
}

export function MultiRoomOverviewView({
  operatorName,
  onCreate,
  onSelect,
}: MultiRoomOverviewProps) {
  const [overview, setOverview] = useState<MultiRoomOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadOverview = useCallback(async () => {
    try {
      const result = await getMultiRoomOverview(operatorName)
      setOverview(result)
      setError(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "多直播间数据加载失败")
    } finally {
      setLoading(false)
    }
  }, [operatorName])

  useEffect(() => {
    setLoading(true)
    void loadOverview()
    const timer = window.setInterval(() => void loadOverview(), 10000)
    return () => window.clearInterval(timer)
  }, [loadOverview])

  const rooms = useMemo(() => overview?.rooms ?? [], [overview])
  const liveCount = useMemo(
    () => rooms.filter((room) => room.session.status === "live").length,
    [rooms],
  )
  const attentionCount = useMemo(
    () =>
      rooms.filter((room) => {
        const level = room.dashboard.latest_insight?.risk_level
        return level === "attention" || level === "critical"
      }).length,
    [rooms],
  )

  return (
    <section className="grid gap-6" aria-labelledby="multi-room-title">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-primary">
            <span className="size-1.5 rounded-full bg-primary shadow-[0_0_0_4px_color-mix(in_oklch,var(--primary)_12%,transparent)]" />
            LIVE OPERATIONS
          </div>
          <h1 id="multi-room-title" className="text-2xl font-semibold tracking-[-0.025em]">
            多直播间总览
          </h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {operatorName}的工作台，每10秒汇总所有正在进行的直播场次。
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void loadOverview()}>
            <RefreshCw data-icon="inline-start" />
            刷新
          </Button>
          <Button onClick={onCreate}>新建直播间</Button>
        </div>
      </div>

      {error && <Alert className="text-destructive">{error}</Alert>}

      <div className="grid gap-3 sm:grid-cols-3">
        <SummaryCard label="活动直播间" value={rooms.length} icon={Radio} tone="primary" />
        <SummaryCard label="正在监控" value={liveCount} icon={Activity} tone="success" />
        <SummaryCard label="需要关注" value={attentionCount} icon={Target} tone="warning" />
      </div>

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((item) => (
            <div key={item} className="h-64 animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
      ) : rooms.length === 0 ? (
        <Card className="border-dashed bg-card/70">
          <CardContent className="grid min-h-64 place-items-center p-6 text-center">
            <div>
              <Radio className="mx-auto size-10 text-muted-foreground" />
              <h2 className="mt-4 text-base font-semibold">暂无活动直播间</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                新建场次并连接浏览器扩展后，这里会同步展示实时状态。
              </p>
              <Button className="mt-4" onClick={onCreate}>
                新建第一个直播间
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {rooms.map((room) => (
            <RoomCard key={room.session.id} room={room} onSelect={onSelect} />
          ))}
        </div>
      )}

      {overview && (
        <p className="text-right text-xs text-muted-foreground">
          汇总更新于 {formatDateTime(overview.updated_at)}
        </p>
      )}
    </section>
  )
}

function SummaryCard({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string
  value: number
  icon: typeof Radio
  tone: "primary" | "success" | "warning"
}) {
  return (
    <Card className="group relative overflow-hidden bg-card/90 transition-[border-color,box-shadow] hover:border-primary/20 hover:shadow-[0_12px_36px_hsl(var(--shadow-color)/0.07)]">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/30 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
      <CardContent className="flex items-center gap-4 p-5">
        <div className={`flex size-11 items-center justify-center rounded-xl ring-1 ring-inset ${
          tone === "success"
            ? "bg-success/10 text-success ring-success/10"
            : tone === "warning"
              ? "bg-warning/12 text-warning-foreground ring-warning/15"
              : "bg-primary/10 text-primary ring-primary/10"
        }`}>
          <Icon className="size-5" />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums tracking-[-0.03em]">{value}</p>
        </div>
      </CardContent>
    </Card>
  )
}

function RoomCard({
  room,
  onSelect,
}: {
  room: LiveRoomOverview
  onSelect: (sessionId: string) => void
}) {
  const { session, dashboard } = room
  const insight = dashboard.latest_insight
  const metrics = dashboard.latest_metrics
  const riskVariant =
    insight?.risk_level === "critical"
      ? "destructive"
      : insight?.risk_level === "attention"
        ? "warning"
        : "success"

  return (
    <Card className="group flex min-w-0 flex-col overflow-hidden bg-card/90 transition-[border-color,box-shadow,transform] duration-200 hover:-translate-y-0.5 hover:border-primary/25 hover:shadow-[0_16px_40px_hsl(var(--shadow-color)/0.08)]">
      <div className="h-0.5 w-full bg-gradient-to-r from-primary/70 via-primary/25 to-transparent opacity-70" />
      <CardHeader className="flex-row items-start justify-between gap-3 pb-4">
        <div className="min-w-0">
          <CardTitle className="truncate text-[15px]">{session.title}</CardTitle>
          <CardDescription className="mt-1 truncate">
            {session.room_name || "未填写直播间备注"}
          </CardDescription>
        </div>
        <Badge variant={session.status === "live" ? "success" : "warning"}>
          {session.status === "live" ? "监控中" : "等待采集"}
        </Badge>
      </CardHeader>
      <CardContent className="grid flex-1 gap-4">
        <div className="grid grid-cols-3 gap-2">
          <RoomMetric
            label="实时在线"
            value={formatInteger(metrics.online_users)}
            icon={UsersRound}
          />
          <RoomMetric
            label="商机数"
            value={formatInteger(metrics.lead_count)}
            icon={Target}
          />
          <RoomMetric
            label="监控时长"
            value={formatDuration(session.duration_seconds)}
            icon={Clock3}
          />
        </div>
        <div className="rounded-lg border border-border/60 bg-muted/65 p-3.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-medium">最新诊断</span>
            <Badge variant={insight ? riskVariant : "secondary"}>
              {insight
                ? insight.risk_level === "critical"
                  ? "立即处理"
                  : insight.risk_level === "attention"
                    ? "需要关注"
                    : "正常"
                : "等待分析"}
            </Badge>
          </div>
          <p className="mt-2 line-clamp-2 min-h-10 text-xs leading-5 text-muted-foreground">
            {insight?.summary || "收到大屏指标和转写后，将自动生成实时诊断。"}
          </p>
        </div>
        <Button className="group/button" variant="outline" onClick={() => onSelect(session.id)}>
          进入控制台
          <ArrowRight data-icon="inline-end" className="transition-transform group-hover/button:translate-x-0.5" />
        </Button>
      </CardContent>
    </Card>
  )
}

function RoomMetric({
  label,
  value,
  icon: Icon,
}: {
  label: string
  value: string
  icon: typeof Radio
}) {
  return (
    <div className="min-w-0 rounded-lg border border-border/70 bg-background/65 p-2.5">
      <div className="flex items-center gap-1 text-muted-foreground">
        <Icon className="size-3" />
        <span className="truncate text-[11px]">{label}</span>
      </div>
      <p className="mt-1.5 truncate text-sm font-semibold tabular-nums tracking-tight">{value}</p>
    </div>
  )
}

function formatInteger(value: number | undefined) {
  if (value === undefined) return "—"
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value)
}
