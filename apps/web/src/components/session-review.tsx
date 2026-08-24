import { useCallback, useEffect, useState } from "react"
import {
  BarChart3,
  CheckCircle2,
  CircleAlert,
  ClipboardCheck,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  Target,
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
import { generateSessionReview, getSessionReview } from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import type { SessionReview } from "@/types"

interface SessionReviewProps {
  sessionId: string
  llmConfigured: boolean
}

export function SessionReviewCard({
  sessionId,
  llmConfigured,
}: SessionReviewProps) {
  const [review, setReview] = useState<SessionReview | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadReview = useCallback(async () => {
    try {
      setReview(await getSessionReview(sessionId))
      setError(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "复盘加载失败")
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    void loadReview()
  }, [loadReview])

  useEffect(() => {
    if (review?.status !== "pending") return
    const timer = window.setInterval(() => void loadReview(), 3000)
    return () => window.clearInterval(timer)
  }, [loadReview, review?.status])

  async function handleGenerate() {
    setGenerating(true)
    setError(null)
    try {
      await generateSessionReview(sessionId)
      await loadReview()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "复盘生成失败")
    } finally {
      setGenerating(false)
    }
  }

  return (
    <Card className="overflow-hidden border-primary/20 bg-card/95">
      <div className="h-0.5 bg-gradient-to-r from-primary via-primary/35 to-transparent" />
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3 border-b border-border/60">
        <div className="grid gap-1">
          <CardTitle className="flex items-center gap-2">
            <ClipboardCheck className="size-4 text-primary" />
            整场直播复盘
          </CardTitle>
          <CardDescription>
            {review?.status === "completed"
              ? `生成于 ${formatDateTime(review.updated_at)}`
              : "综合整场转写、实时指标和AI诊断生成。"}
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          {review && <ReviewStatusBadge review={review} />}
          <Button
            variant={review ? "outline" : "default"}
            size="sm"
            disabled={!llmConfigured || generating || review?.status === "pending"}
            onClick={handleGenerate}
          >
            {generating || review?.status === "pending" ? (
              <LoaderCircle data-icon="inline-start" className="animate-spin" />
            ) : (
              <RefreshCw data-icon="inline-start" />
            )}
            {review ? "重新生成" : "生成复盘"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4">
        {error && <Alert className="text-destructive">{error}</Alert>}
        {loading || review?.status === "pending" ? (
          <div className="grid min-h-40 place-items-center text-center">
            <div>
              <LoaderCircle className="mx-auto size-8 animate-spin text-primary" />
              <p className="mt-3 text-sm font-medium">正在分析整场直播</p>
              <p className="mt-1 text-xs text-muted-foreground">
                转写内容较多时通常需要几十秒，请保持页面打开。
              </p>
            </div>
          </div>
        ) : review?.status === "completed" ? (
          <CompletedReview review={review} />
        ) : (
          <div className="grid min-h-40 place-items-center text-center">
            <div>
              <Sparkles className="mx-auto size-8 text-muted-foreground" />
              <p className="mt-3 text-sm font-medium">
                {review?.status === "failed" ? "本次复盘生成失败" : "等待生成整场复盘"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {review?.error ||
                  (llmConfigured
                    ? "结束场次后会自动生成，也可以点击右上角手动生成。"
                    : "大模型尚未配置，暂时无法生成复盘。")}
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function ReviewStatusBadge({ review }: { review: SessionReview }) {
  return (
    <Badge
      variant={
        review.status === "completed"
          ? "success"
          : review.status === "failed"
            ? "destructive"
            : "warning"
      }
    >
      {review.status === "completed"
        ? "已完成"
        : review.status === "failed"
          ? "生成失败"
          : "生成中"}
    </Badge>
  )
}

function CompletedReview({ review }: { review: SessionReview }) {
  return (
    <div className="grid gap-4">
      <Alert className="grid gap-1 border-primary/25 bg-primary/5 shadow-none">
        <span className="text-xs font-medium text-primary">整场结论</span>
        <span className="text-sm leading-6">{review.summary}</span>
      </Alert>
      {review.metric_summary && (
        <div className="flex items-start gap-2 rounded-lg border border-border/60 bg-muted/65 p-3.5 text-sm leading-6">
          <BarChart3 className="mt-1 size-4 shrink-0 text-primary" />
          <span>{review.metric_summary}</span>
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        <ReviewList
          title="表现亮点"
          icon={CheckCircle2}
          items={review.highlights}
        />
        <ReviewList title="主要问题" icon={CircleAlert} items={review.issues} />
        <ReviewList title="下场动作" icon={Target} items={review.actions} numbered />
      </div>
    </div>
  )
}

function ReviewList({
  title,
  icon: Icon,
  items,
  numbered = false,
}: {
  title: string
  icon: typeof Target
  items: string[]
  numbered?: boolean
}) {
  return (
    <section className="rounded-xl border border-border/70 bg-background/45 p-4">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <Icon className="size-4 text-primary" />
        {title}
      </h3>
      {items.length > 0 ? (
        <ol className="mt-3 grid gap-2">
          {items.map((item, index) => (
            <li key={item} className="flex items-start gap-2 text-xs leading-5">
              <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md bg-primary/8 text-[10px] font-semibold text-primary">
                {numbered ? index + 1 : "·"}
              </span>
              <span>{item}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-3 text-xs text-muted-foreground">暂无内容</p>
      )}
    </section>
  )
}
