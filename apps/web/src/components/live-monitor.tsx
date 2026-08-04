import { useEffect, useMemo, useRef, useState } from "react"
import {
  AudioLines,
  CheckCircle2,
  CircleStop,
  Clock3,
  Copy,
  Headphones,
  Info,
  Radio,
  RotateCcw,
  Server,
  TriangleAlert,
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
import { WS_BASE, audioUrl, endSession } from "@/lib/api"
import {
  cn,
  formatDateTime,
  formatDuration,
} from "@/lib/utils"
import type {
  MonitorEvent,
  SessionDetail,
  TranscriptItem,
} from "@/types"

const platformNames = {
  douyin: "抖音",
  dongchedi: "懂车云店",
}

interface LiveMonitorProps {
  session: SessionDetail
  onRefresh: () => Promise<void>
}

export function LiveMonitor({ session, onRefresh }: LiveMonitorProps) {
  const [transcripts, setTranscripts] = useState(session.transcripts)
  const [audioConnected, setAudioConnected] = useState(false)
  const [socketConnected, setSocketConnected] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [ending, setEnding] = useState(false)
  const [now, setNow] = useState(Date.now())
  const transcriptEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setTranscripts(session.transcripts)
  }, [session])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    const socket = new WebSocket(`${WS_BASE}/ws/monitor/${session.id}`)
    let heartbeat: number | undefined
    let active = true
    socket.onopen = () => {
      if (!active) return
      setSocketConnected(true)
      setMessage(null)
      heartbeat = window.setInterval(() => socket.send("ping"), 15000)
    }
    socket.onmessage = (event) => {
      if (!active) return
      const data = JSON.parse(event.data) as MonitorEvent
      if (data.type === "transcript") {
        const transcript = data.payload as unknown as TranscriptItem
        setTranscripts((current) => {
          if (current.some((item) => item.id === transcript.id)) return current
          return [...current, transcript]
        })
      }
      if (data.type === "session") {
        void onRefresh()
      }
      if (data.type === "audio_status") {
        const connected = Boolean(data.payload.connected)
        setAudioConnected(connected)
        setMessage(String(data.payload.message ?? ""))
        if (!connected) void onRefresh()
      }
      if (data.type === "warning") {
        setMessage(String(data.payload.message ?? "实时通道出现异常"))
      }
    }
    socket.onclose = () => {
      if (active) setSocketConnected(false)
    }
    socket.onerror = () => {
      if (active) setMessage("浏览器实时通道连接失败")
    }
    return () => {
      active = false
      if (heartbeat) window.clearInterval(heartbeat)
      socket.close()
    }
  }, [onRefresh, session.id])

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [transcripts])

  const duration = useMemo(() => {
    if (!session.started_at) return session.duration_seconds
    const start = new Date(session.started_at).getTime()
    const end = session.ended_at
      ? new Date(session.ended_at).getTime()
      : now
    return Math.max(0, Math.floor((end - start) / 1000))
  }, [now, session])

  async function handleEnd() {
    setEnding(true)
    try {
      await endSession(session.id)
      await onRefresh()
    } finally {
      setEnding(false)
    }
  }

  async function copySessionId() {
    await navigator.clipboard.writeText(session.id)
    setMessage("场次ID已复制，可粘贴到Windows采集助手")
  }

  return (
    <div className="grid min-h-0 gap-4">
      <section className="flex flex-col gap-3 border-b pb-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge>
              {platformNames[session.platform]}
            </Badge>
            <Badge
              variant={
                session.status === "live"
                  ? "success"
                  : session.status === "failed"
                    ? "destructive"
                    : "secondary"
              }
            >
              {session.status === "live"
                ? "监控中"
                : session.status === "created"
                  ? "等待采集"
                  : session.status === "failed"
                    ? "异常结束"
                    : "已结束"}
            </Badge>
          </div>
          <h1 className="truncate text-xl font-semibold tracking-tight">
            {session.title}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {session.room_name || "未填写直播间备注"} · 优化师：
            {session.operator_name}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={copySessionId}>
            <Copy data-icon="inline-start" />
            复制场次ID
          </Button>
          <Button variant="outline" onClick={onRefresh}>
            <RotateCcw data-icon="inline-start" />
            刷新
          </Button>
          {(session.status === "created" || session.status === "live") && (
            <Button
              variant="destructive"
              onClick={handleEnd}
              disabled={ending}
            >
              <CircleStop data-icon="inline-start" />
              结束场次
            </Button>
          )}
        </div>
      </section>

      <div className="grid gap-3 md:grid-cols-3">
        <StatusMetric
          icon={AudioLines}
          label="音频采集"
          value={audioConnected ? "已连接" : "等待连接"}
          state={audioConnected ? "success" : "warning"}
        />
        <StatusMetric
          icon={Server}
          label="实时通道"
          value={socketConnected ? "正常" : "连接中"}
          state={socketConnected ? "success" : "warning"}
        />
        <StatusMetric
          icon={Clock3}
          label="监控时长"
          value={formatDuration(duration)}
          state="default"
        />
      </div>

      {message && (
        <Alert className="flex items-center gap-2">
          <Info className="size-4 shrink-0 text-primary" />
          <span>{message}</span>
        </Alert>
      )}

      <div className="grid min-h-0 gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <Card className="flex min-h-[520px] flex-col overflow-hidden">
          <CardHeader className="flex-row items-start justify-between gap-4 border-b">
            <div className="grid gap-1">
              <CardTitle className="flex items-center gap-2">
                <Headphones className="size-4 text-primary" />
                实时转写
              </CardTitle>
              <CardDescription>
                文字将随音频识别结果持续追加。
              </CardDescription>
            </div>
            <Badge variant="secondary">
              {transcripts.length} 条
            </Badge>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 overflow-y-auto p-0">
            {transcripts.length === 0 ? (
              <div className="flex min-h-[420px] flex-col items-center justify-center px-6 text-center">
                <div className="mb-4 flex size-12 items-center justify-center rounded-xl bg-muted">
                  <AudioLines className="size-6 text-muted-foreground" />
                </div>
                <h2 className="text-sm font-semibold">等待实时文字</h2>
                <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">
                  在Windows采集助手中输入场次ID并启动采集。当前默认ASR为模拟适配器，不会识别真实语音。
                </p>
              </div>
            ) : (
              <ol className="divide-y">
                {transcripts.map((item) => (
                  <li
                    key={item.id}
                    className="grid grid-cols-[72px_minmax(0,1fr)] gap-4 px-4 py-3"
                  >
                    <time className="pt-0.5 text-xs tabular-nums text-muted-foreground">
                      {formatDuration(Math.floor(item.start_ms / 1000))}
                    </time>
                    <p className="text-sm leading-6">{item.text}</p>
                  </li>
                ))}
                <div ref={transcriptEndRef} />
              </ol>
            )}
          </CardContent>
        </Card>

        <div className="grid content-start gap-4">
          <Card>
            <CardHeader>
              <CardTitle>场次信息</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 text-sm">
              <InfoRow label="创建时间" value={formatDateTime(session.created_at)} />
              <InfoRow label="开始时间" value={formatDateTime(session.started_at)} />
              <InfoRow label="结束时间" value={formatDateTime(session.ended_at)} />
              <InfoRow label="场次ID" value={session.id.slice(0, 8)} mono />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>录音文件</CardTitle>
              <CardDescription>
                采集助手断开后，WAV文件会完成封装。
              </CardDescription>
            </CardHeader>
            <CardContent>
              {session.audio_path ? (
                <audio
                  className="h-9 w-full"
                  controls
                  preload="metadata"
                  src={audioUrl(session.id)}
                >
                  浏览器不支持音频播放。
                </audio>
              ) : (
                <p className="text-sm text-muted-foreground">暂无录音</p>
              )}
            </CardContent>
          </Card>

          <Alert className="grid gap-2 border-warning/40 bg-warning/8">
            <div className="flex items-center gap-2 font-medium">
              <TriangleAlert className="size-4 text-warning" />
              开发模式提示
            </div>
            <p className="text-xs leading-5 text-muted-foreground">
              当前模拟ASR只验证传输链路。选择供应商并配置密钥后，才会显示真实语音内容。
            </p>
          </Alert>
        </div>
      </div>
    </div>
  )
}

function StatusMetric({
  icon: Icon,
  label,
  value,
  state,
}: {
  icon: typeof Radio
  label: string
  value: string
  state: "default" | "success" | "warning"
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-3">
        <div
          className={cn(
            "flex size-9 items-center justify-center rounded-lg bg-muted text-muted-foreground",
            state === "success" && "bg-success/12 text-success",
            state === "warning" && "bg-warning/18 text-warning-foreground",
          )}
        >
          {state === "success" ? (
            <CheckCircle2 className="size-4" />
          ) : (
            <Icon className="size-4" />
          )}
        </div>
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="mt-0.5 text-sm font-semibold tabular-nums">{value}</p>
        </div>
      </CardContent>
    </Card>
  )
}

function InfoRow({
  label,
  value,
  mono = false,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("truncate text-right", mono && "font-mono text-xs")}>
        {value}
      </span>
    </div>
  )
}
