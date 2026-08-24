import {
  Activity,
  BarChart3,
  Bot,
  CircleAlert,
  Clock3,
  Eye,
  Gauge,
  Heart,
  Lightbulb,
  MessageCircle,
  MessageSquareText,
  MousePointerClick,
  Radio,
  ReceiptText,
  Share2,
  Sparkles,
  Target,
  ThumbsUp,
  UserPlus,
  UsersRound,
  WalletCards,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"

import { Alert } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { formatDateTime } from "@/lib/utils"
import type { AiInsight } from "@/types"

type MetricFormatter = (value: number) => string

interface SecondaryMetricDefinition {
  key: string
  label: string
  format: MetricFormatter
}

interface MetricDefinition {
  key: string
  label: string
  icon: LucideIcon
  format: MetricFormatter
  secondary?: SecondaryMetricDefinition
}

interface MetricGroup {
  title: string
  metrics: MetricDefinition[]
}

function formatInteger(value: number) {
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 0,
  }).format(value)
}

function formatPercent(value: number) {
  return `${value.toFixed(2)}%`
}

function formatDecimal(value: number) {
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 2,
  }).format(value)
}

function formatDuration(value: number) {
  const totalSeconds = Math.max(0, Math.round(value))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (hours > 0) return `${hours}时${minutes}分${seconds}秒`
  if (minutes > 0) return `${minutes}分${seconds}秒`
  return `${seconds}秒`
}

const metricGroups: MetricGroup[] = [
  {
    title: "核心指标",
    metrics: [
      {
        key: "average_watch_seconds",
        label: "人均观看时长",
        icon: Clock3,
        format: formatDuration,
        secondary: {
          key: "fans_average_watch_seconds",
          label: "粉丝停留",
          format: formatDuration,
        },
      },
      {
        key: "lead_count",
        label: "全场景商机数",
        icon: Target,
        format: formatInteger,
        secondary: {
          key: "lead_conversion_rate",
          label: "线索转化率",
          format: formatPercent,
        },
      },
      {
        key: "private_message_users",
        label: "私信人数",
        icon: MessageCircle,
        format: formatInteger,
      },
      {
        key: "online_users",
        label: "实时在线人数",
        icon: Radio,
        format: formatInteger,
        secondary: {
          key: "preview_viewers",
          label: "看过",
          format: formatInteger,
        },
      },
    ],
  },
  {
    title: "流量与观看",
    metrics: [
      {
        key: "cumulative_viewers",
        label: "累计观看人数",
        icon: UsersRound,
        format: formatInteger,
        secondary: {
          key: "fans_viewer_rate",
          label: "粉丝占比",
          format: formatPercent,
        },
      },
      {
        key: "exposure_entry_rate",
        label: "曝光进入率",
        icon: Activity,
        format: formatPercent,
        secondary: {
          key: "fans_exposure_entry_rate",
          label: "粉丝曝光进入率",
          format: formatPercent,
        },
      },
      {
        key: "peak_online_users",
        label: "最高在线人数",
        icon: Gauge,
        format: formatInteger,
        secondary: {
          key: "average_online_users",
          label: "平均在线",
          format: formatInteger,
        },
      },
      {
        key: "watch_over_one_minute",
        label: "大于1分钟观看人次",
        icon: Eye,
        format: formatInteger,
      },
      {
        key: "exposure_count",
        label: "曝光次数",
        icon: BarChart3,
        format: formatInteger,
        secondary: {
          key: "fans_exposure_share",
          label: "粉丝占比",
          format: formatPercent,
        },
      },
    ],
  },
  {
    title: "转化与经营",
    metrics: [
      {
        key: "spend",
        label: "消耗",
        icon: WalletCards,
        format: formatDecimal,
        secondary: {
          key: "lead_cost",
          label: "线索成本",
          format: formatDecimal,
        },
      },
      {
        key: "windmill_clicks",
        label: "小风车点击次数",
        icon: MousePointerClick,
        format: formatInteger,
        secondary: {
          key: "windmill_click_rate",
          label: "点击率",
          format: formatPercent,
        },
      },
      {
        key: "new_followers",
        label: "涨粉量",
        icon: UserPlus,
        format: formatInteger,
        secondary: {
          key: "follower_rate",
          label: "涨粉率",
          format: formatPercent,
        },
      },
      {
        key: "card_clicks",
        label: "卡片点击次数",
        icon: MousePointerClick,
        format: formatInteger,
        secondary: {
          key: "card_click_rate",
          label: "点击率",
          format: formatPercent,
        },
      },
      {
        key: "fan_club_joins",
        label: "加粉丝团人数",
        icon: Heart,
        format: formatInteger,
        secondary: {
          key: "fan_club_join_rate",
          label: "加团率",
          format: formatPercent,
        },
      },
      {
        key: "form_submits",
        label: "表单提交数",
        icon: ReceiptText,
        format: formatInteger,
        secondary: {
          key: "form_cost",
          label: "表单成本",
          format: formatDecimal,
        },
      },
    ],
  },
  {
    title: "互动表现",
    metrics: [
      {
        key: "comment_rate",
        label: "评论率",
        icon: MessageSquareText,
        format: formatPercent,
        secondary: {
          key: "comment_users",
          label: "评论人数",
          format: formatInteger,
        },
      },
      {
        key: "interaction_rate",
        label: "互动率",
        icon: Activity,
        format: formatPercent,
        secondary: {
          key: "interaction_users",
          label: "互动人数",
          format: formatInteger,
        },
      },
      {
        key: "like_rate",
        label: "点赞率",
        icon: ThumbsUp,
        format: formatPercent,
        secondary: {
          key: "like_users",
          label: "点赞人数",
          format: formatInteger,
        },
      },
      {
        key: "share_rate",
        label: "分享率",
        icon: Share2,
        format: formatPercent,
        secondary: {
          key: "share_users",
          label: "分享人数",
          format: formatInteger,
        },
      },
      {
        key: "like_count",
        label: "点赞次数",
        icon: ThumbsUp,
        format: formatInteger,
      },
      {
        key: "share_count",
        label: "分享次数",
        icon: Share2,
        format: formatInteger,
      },
      {
        key: "comment_count",
        label: "评论次数",
        icon: MessageSquareText,
        format: formatInteger,
      },
      {
        key: "tip_count",
        label: "打赏次数",
        icon: WalletCards,
        format: formatInteger,
      },
      {
        key: "interaction_count",
        label: "互动次数",
        icon: Activity,
        format: formatInteger,
      },
    ],
  },
]

interface AiDashboardProps {
  metrics: Record<string, number>
  metricAt: string | null
  insight: AiInsight | null
  llmConfigured: boolean
  llmModel: string
}

export function AiDashboard({
  metrics,
  metricAt,
  insight,
  llmConfigured,
  llmModel,
}: AiDashboardProps) {
  const hasMetrics = Object.keys(metrics).length > 0

  return (
    <section className="grid gap-5" aria-labelledby="ai-dashboard-title">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-primary">
            Intelligence Center
          </p>
          <h2
            id="ai-dashboard-title"
            className="flex items-center gap-2 text-lg font-semibold tracking-[-0.02em]"
          >
            <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary ring-1 ring-inset ring-primary/10">
              <Sparkles className="size-4" />
            </span>
            AI实时盯播
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            综合大屏指标与主播话术，每60秒刷新诊断和动作建议。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={hasMetrics ? "success" : "secondary"}>
            {hasMetrics ? "大屏数据已接入" : "等待浏览器扩展"}
          </Badge>
          <Badge variant="outline">{llmModel}</Badge>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="overflow-hidden border-primary/20 bg-card/95">
          <div className="h-0.5 bg-gradient-to-r from-primary via-primary/35 to-transparent" />
          <CardHeader className="flex-row items-start justify-between gap-3 border-b border-border/60">
            <div className="grid gap-1">
              <CardTitle className="flex items-center gap-2">
                <Bot className="size-4 text-primary" />
                实时诊断
              </CardTitle>
              <CardDescription>
                {insight
                  ? `更新于 ${formatDateTime(insight.created_at)}`
                  : metricAt
                    ? `指标更新于 ${formatDateTime(metricAt)}`
                    : "尚未收到大屏指标"}
              </CardDescription>
            </div>
            {insight && (
              <Badge
                variant={
                  insight.risk_level === "critical"
                    ? "destructive"
                    : insight.risk_level === "attention"
                      ? "warning"
                      : "success"
                }
              >
                {insight.risk_level === "critical"
                  ? "需立即处理"
                  : insight.risk_level === "attention"
                    ? "需要关注"
                    : "表现正常"}
              </Badge>
            )}
          </CardHeader>
          <CardContent className="grid gap-4">
            {insight ? (
              <>
                <p className="text-sm font-medium leading-6">{insight.summary}</p>
                <div className="grid gap-2">
                  {insight.signals.map((signal) => (
                    <div
                      key={signal}
                      className="flex items-start gap-2 rounded-lg border border-border/50 bg-muted/65 px-3 py-2.5 text-sm"
                    >
                      <CircleAlert className="mt-0.5 size-4 shrink-0 text-warning" />
                      <span>{signal}</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="grid min-h-36 place-items-center text-center">
                <div>
                  <Bot className="mx-auto size-8 text-muted-foreground" />
                  <p className="mt-3 text-sm font-medium">
                    {llmConfigured ? "等待生成第一轮诊断" : "大模型尚未配置"}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {llmConfigured
                      ? "浏览器扩展上传大屏数据后将自动分析。"
                      : "配置 DeepSeek API Key 后即可启用实时大模型分析。"}
                  </p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="overflow-hidden border-primary/20 bg-card/95">
          <div className="h-0.5 bg-gradient-to-r from-primary/70 via-primary/20 to-transparent" />
          <CardHeader className="border-b border-border/60">
            <CardTitle className="flex items-center gap-2">
              <Lightbulb className="size-4 text-primary" />
              建议动作与话术
            </CardTitle>
            <CardDescription>按优先级给优化师和主播执行。</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            {insight ? (
              <>
                <ol className="grid gap-2">
                  {insight.actions.map((action, index) => (
                    <li
                      key={action}
                      className="grid grid-cols-[26px_minmax(0,1fr)] gap-2.5 rounded-lg px-1 py-1 text-sm leading-6"
                    >
                      <span className="flex size-6 items-center justify-center rounded-lg bg-primary/10 text-xs font-semibold text-primary ring-1 ring-inset ring-primary/10">
                        {index + 1}
                      </span>
                      <span>{action}</span>
                    </li>
                  ))}
                </ol>
                {insight.talk_track && (
                  <Alert className="grid gap-1 border-primary/25 bg-primary/5 shadow-none">
                    <span className="text-xs font-medium text-primary">
                      推荐主播下一句
                    </span>
                    <span className="text-sm leading-6">
                      “{insight.talk_track}”
                    </span>
                  </Alert>
                )}
              </>
            ) : (
              <p className="py-12 text-center text-sm text-muted-foreground">
                生成诊断后，这里会显示建议动作和可直接使用的话术。
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6">
        {metricGroups.map((group) => (
          <section key={group.title} className="grid gap-3">
            <div className="flex items-center gap-3">
              <h3 className="whitespace-nowrap text-xs font-semibold tracking-wide text-muted-foreground">
                {group.title}
              </h3>
              <div className="h-px flex-1 bg-border/70" />
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {group.metrics.map((definition) => (
                <MetricCard
                  key={definition.key}
                  definition={definition}
                  metrics={metrics}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </section>
  )
}

function MetricCard({
  definition,
  metrics,
}: {
  definition: MetricDefinition
  metrics: Record<string, number>
}) {
  const { key, label, icon: Icon, format, secondary } = definition
  const value = metrics[key]
  const secondaryValue = secondary ? metrics[secondary.key] : undefined

  return (
    <Card className="group min-w-0 bg-card/85 transition-[border-color,box-shadow,transform] duration-200 hover:-translate-y-0.5 hover:border-primary/20 hover:shadow-[0_12px_30px_hsl(var(--shadow-color)/0.065)]">
      <CardContent className="grid min-h-28 content-between gap-3 p-4">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <span className="truncate text-xs font-medium text-muted-foreground">
            {label}
          </span>
          <span className="flex size-7 items-center justify-center rounded-lg bg-muted text-muted-foreground transition-colors group-hover:bg-primary/8 group-hover:text-primary">
            <Icon className="size-3.5 shrink-0" />
          </span>
        </div>
        <strong className="truncate text-[1.35rem] font-semibold tabular-nums tracking-[-0.03em]">
          {value === undefined ? "—" : format(value)}
        </strong>
        <div className="min-h-5 truncate text-xs text-muted-foreground">
          {secondary && (
            <>
              {secondary.label}{" "}
              <span className="font-medium tabular-nums text-foreground">
                {secondaryValue === undefined
                  ? "—"
                  : secondary.format(secondaryValue)}
              </span>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
