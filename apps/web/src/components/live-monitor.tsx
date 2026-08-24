import { useEffect, useMemo, useRef, useState } from "react"
import {
  ArrowDownToLine,
  AudioLines,
  CheckCircle2,
  CircleStop,
  Clock3,
  Copy,
  ExternalLink,
  Headphones,
  Info,
  LoaderCircle,
  Play,
  Radio,
  RotateCcw,
  ScanSearch,
  Server,
  Square,
  TriangleAlert,
} from "lucide-react"

import { AiDashboard } from "@/components/ai-dashboard"
import { SessionReviewCard } from "@/components/session-review"
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
import {
  WS_BASE,
  audioUrl,
  endSession,
  getLiveDashboard,
  probeLiveSource,
  startLiveSource,
  stopLiveSource,
} from "@/lib/api"
import {
  cn,
  formatDateTime,
  formatDuration,
} from "@/lib/utils"
import type {
  AudioSourceStatus,
  AiInsight,
  MonitorEvent,
  LiveSourceProbeResult,
  SessionDetail,
  MetricSnapshot,
  TranscriptItem,
} from "@/types"

const platformNames = {
  douyin: "抖音",
  dongchedi: "懂车云店",
}

interface LiveMonitorProps {
  session: SessionDetail
  asrProvider: string
  asrConfigured: boolean
  llmConfigured: boolean
  llmModel: string
  onRefresh: () => Promise<void>
}

export function LiveMonitor({
  session,
  asrProvider,
  asrConfigured,
  llmConfigured,
  llmModel,
  onRefresh,
}: LiveMonitorProps) {
  const [transcripts, setTranscripts] = useState(session.transcripts)
  const [audioConnected, setAudioConnected] = useState(false)
  const [audioActive, setAudioActive] = useState(false)
  const [audioSource, setAudioSource] =
    useState<AudioSourceStatus["source"]>(null)
  const [socketConnected, setSocketConnected] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [metrics, setMetrics] = useState<Record<string, number>>({})
  const [latestMetricAt, setLatestMetricAt] = useState<string | null>(null)
  const [insight, setInsight] = useState<AiInsight | null>(null)
  const [ending, setEnding] = useState(false)
  const [probing, setProbing] = useState(false)
  const [probeResult, setProbeResult] =
    useState<LiveSourceProbeResult | null>(null)
  const [linkAction, setLinkAction] =
    useState<"start" | "stop" | null>(null)
  const [now, setNow] = useState(Date.now())
  const [followingTranscripts, setFollowingTranscripts] = useState(true)
  const transcriptScrollRef = useRef<HTMLDivElement>(null)
  const shouldFollowTranscriptsRef = useRef(true)

  useEffect(() => {
    setTranscripts(session.transcripts)
  }, [session])

  useEffect(() => {
    shouldFollowTranscriptsRef.current = true
    setFollowingTranscripts(true)
  }, [session.id])

  useEffect(() => {
    let active = true
    const loadDashboard = () => {
      void getLiveDashboard(session.id)
        .then((dashboard) => {
          if (!active) return
          setMetrics(dashboard.latest_metrics)
          setLatestMetricAt(dashboard.latest_metric_at)
          setInsight(dashboard.latest_insight)
        })
        .catch(() => {
          if (active) setMessage("实时大屏数据加载失败")
        })
    }
    loadDashboard()
    const timer = window.setInterval(loadDashboard, 10000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [session.id])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    let socket: WebSocket | null = null
    let heartbeat: number | undefined
    let reconnectTimer: number | undefined
    let reconnectDelay = 1000
    let active = true

    const connect = () => {
      const currentSocket = new WebSocket(
        `${WS_BASE}/ws/monitor/${session.id}`,
      )
      socket = currentSocket
      currentSocket.onopen = () => {
        if (!active || socket !== currentSocket) return
        setSocketConnected(true)
        setMessage(null)
        reconnectDelay = 1000
        if (heartbeat) window.clearInterval(heartbeat)
        heartbeat = window.setInterval(() => {
          if (currentSocket.readyState === WebSocket.OPEN) {
            currentSocket.send("ping")
          }
        }, 15000)
      }
      currentSocket.onmessage = (event) => {
        if (!active || socket !== currentSocket) return
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
          setAudioActive(Boolean(data.payload.active))
          const source = data.payload.source
          setAudioSource(
            source === "windows" ||
              source === "browser_extension" ||
              source === "live_url"
              ? source
              : null,
          )
          setMessage(String(data.payload.message ?? ""))
          if (!connected) void onRefresh()
        }
        if (data.type === "warning") {
          setMessage(String(data.payload.message ?? "实时通道出现异常"))
        }
        if (data.type === "metrics") {
          const snapshot = data.payload as unknown as MetricSnapshot
          setMetrics((current) => ({ ...current, ...snapshot.normalized }))
          setLatestMetricAt(snapshot.captured_at)
        }
        if (data.type === "ai_insight") {
          setInsight(data.payload as unknown as AiInsight)
        }
      }
      currentSocket.onclose = () => {
        if (!active || socket !== currentSocket) return
        if (heartbeat) window.clearInterval(heartbeat)
        heartbeat = undefined
        setSocketConnected(false)
        reconnectTimer = window.setTimeout(connect, reconnectDelay)
        reconnectDelay = Math.min(10000, reconnectDelay * 2)
      }
      currentSocket.onerror = () => {
        if (!active || socket !== currentSocket) return
        setMessage("实时通道暂时断开，正在自动重连")
        currentSocket.close()
      }
    }

    connect()
    return () => {
      active = false
      if (heartbeat) window.clearInterval(heartbeat)
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [onRefresh, session.id])

  useEffect(() => {
    if (!shouldFollowTranscriptsRef.current) return

    const frame = window.requestAnimationFrame(() => {
      const container = transcriptScrollRef.current
      if (container) container.scrollTop = container.scrollHeight
    })
    return () => window.cancelAnimationFrame(frame)
  }, [transcripts.length])

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
    setMessage("场次ID已复制，可粘贴到浏览器扩展")
  }

  async function handleProbe() {
    setProbing(true)
    setProbeResult(null)
    try {
      const result = await probeLiveSource(session.id)
      setProbeResult(result)
      setMessage(result.message)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "链接抓取测试失败")
    } finally {
      setProbing(false)
    }
  }

  function applyAudioStatus(status: AudioSourceStatus) {
    setAudioActive(status.active)
    setAudioConnected(status.connected)
    setAudioSource(status.source)
    setMessage(status.message)
  }

  async function handleStartLinkListening() {
    setLinkAction("start")
    try {
      applyAudioStatus(await startLiveSource(session.id))
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "链接监听启动失败")
    } finally {
      setLinkAction(null)
    }
  }

  async function handleStopLinkListening() {
    setLinkAction("stop")
    try {
      applyAudioStatus(await stopLiveSource(session.id))
      await onRefresh()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "链接监听停止失败")
    } finally {
      setLinkAction(null)
    }
  }

  function handleTranscriptScroll() {
    const container = transcriptScrollRef.current
    if (!container) return

    const distanceToBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight
    const shouldFollow = distanceToBottom <= 48
    shouldFollowTranscriptsRef.current = shouldFollow
    setFollowingTranscripts(shouldFollow)
  }

  function jumpToLatestTranscript() {
    shouldFollowTranscriptsRef.current = true
    setFollowingTranscripts(true)
    const container = transcriptScrollRef.current
    container?.scrollTo({ top: container.scrollHeight, behavior: "smooth" })
  }

  const directListening = audioActive && audioSource === "live_url"
  const extensionPreferred =
    session.platform === "dongchedi" ||
    session.live_url.includes("autoengine.com")

  return (
    <div className="grid min-h-0 gap-5">
      <section className="flex flex-col gap-4 border-b border-border/70 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="mb-2.5 flex flex-wrap items-center gap-2">
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
          <h1 className="truncate text-2xl font-semibold tracking-[-0.025em]">
            {session.title}
          </h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {session.room_name || "未填写直播间备注"} · 优化师：
            {session.operator_name}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {session.live_url && (
            <>
              {!extensionPreferred &&
                (session.status === "created" ||
                session.status === "live" ||
                (session.status === "failed" &&
                  session.transcript_count === 0 &&
                  session.duration_seconds <= 5)) &&
                (directListening ? (
                  <Button
                    variant="outline"
                    onClick={handleStopLinkListening}
                    disabled={linkAction !== null}
                  >
                    {linkAction === "stop" ? (
                      <LoaderCircle
                        data-icon="inline-start"
                        className="animate-spin"
                      />
                    ) : (
                      <Square data-icon="inline-start" />
                    )}
                    {linkAction === "stop" ? "正在停止" : "停止链接监听"}
                  </Button>
                ) : (
                  <Button
                    onClick={handleStartLinkListening}
                    disabled={audioActive || linkAction !== null}
                  >
                    {linkAction === "start" ? (
                      <LoaderCircle
                        data-icon="inline-start"
                        className="animate-spin"
                      />
                    ) : (
                      <Play data-icon="inline-start" />
                    )}
                    {linkAction === "start"
                      ? "正在启动"
                      : session.status === "failed"
                        ? "重新开始链接监听"
                        : "开始链接监听"}
                  </Button>
                ))}
              {!extensionPreferred && (
                <Button
                  variant="outline"
                  onClick={handleProbe}
                  disabled={probing || audioActive}
                >
                  <ScanSearch data-icon="inline-start" />
                  {probing ? "正在测试" : "仅测试链接"}
                </Button>
              )}
              <Button asChild variant="outline">
                <a
                  href={session.live_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ExternalLink data-icon="inline-start" />
                  打开直播间
                </a>
              </Button>
            </>
          )}
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
          value={
            audioConnected
              ? audioSource === "live_url"
                ? "链接监听中"
                : audioSource === "browser_extension"
                  ? "浏览器扩展已连接"
                  : "采集助手已连接"
              : audioActive
                ? "正在连接"
                : "等待连接"
          }
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

      {extensionPreferred && !audioConnected && (
        <Alert className="flex items-start gap-2 border-primary/30 bg-primary/5">
          <Info className="mt-0.5 size-4 shrink-0 text-primary" />
          <span>
            请先复制场次ID，再到懂车云店直播标签页中打开“汽车直播盯播助手”扩展并开始采集。
          </span>
        </Alert>
      )}

      {audioConnected &&
        audioSource === "browser_extension" &&
        Object.keys(metrics).length === 0 && (
          <Alert className="flex items-start gap-2 border-warning/40 bg-warning/8">
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" />
            <span>
              浏览器扩展的音频已连接，但尚未收到大屏监控数据。请确认扩展绑定的是当前场次，并刷新一次懂车云店直播大屏；扩展弹窗会显示最后上传时间或错误原因。
            </span>
          </Alert>
        )}

      {probeResult?.status === "live" && (
        <Alert className="flex flex-wrap items-center gap-x-2 gap-y-1 border-success/40 bg-success/8">
          <CheckCircle2 className="size-4 shrink-0 text-success" />
          <span>
            {probeResult.message}
            {!directListening && "，请点击“开始链接监听”"}
          </span>
          {probeResult.author && (
            <span className="text-muted-foreground">
              主播：{probeResult.author}
            </span>
          )}
          {probeResult.qualities.length > 0 && (
            <span className="text-muted-foreground">
              清晰度：{probeResult.qualities.join("、")}
            </span>
          )}
        </Alert>
      )}

      {(session.status === "ended" || session.status === "failed") && (
        <SessionReviewCard
          sessionId={session.id}
          llmConfigured={llmConfigured}
        />
      )}

      <div className="grid min-h-0 items-start gap-5 xl:grid-cols-[minmax(300px,0.62fr)_minmax(0,1.55fr)] 2xl:grid-cols-[minmax(330px,0.58fr)_minmax(0,1.65fr)]">
        <div className="grid min-w-0 gap-4">
          <Card className="flex h-[420px] min-h-0 flex-col overflow-hidden bg-card/90 xl:h-[470px]">
            <CardHeader className="flex-row flex-wrap items-start justify-between gap-3 border-b border-border/60 bg-muted/20">
              <div className="grid gap-1">
                <CardTitle className="flex items-center gap-2">
                  <Headphones className="size-4 text-primary" />
                  实时转写
                </CardTitle>
                <CardDescription>
                  新内容仅在当前位于底部时自动跟随。
                </CardDescription>
              </div>
              <div className="ml-auto flex shrink-0 items-center gap-2">
                {!followingTranscripts && transcripts.length > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={jumpToLatestTranscript}
                  >
                    <ArrowDownToLine data-icon="inline-start" />
                    回到最新
                  </Button>
                )}
                <Badge variant={followingTranscripts ? "secondary" : "outline"}>
                  {followingTranscripts ? "跟随最新" : "已暂停"} ·{" "}
                  {transcripts.length} 条
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="min-h-0 flex-1 p-0">
              <div
                ref={transcriptScrollRef}
                className="h-full overflow-y-auto overscroll-contain"
                onScroll={handleTranscriptScroll}
              >
                {transcripts.length === 0 ? (
                  <div className="flex min-h-full flex-col items-center justify-center px-6 text-center">
                    <div className="mb-4 flex size-12 items-center justify-center rounded-xl bg-muted">
                      <AudioLines className="size-6 text-muted-foreground" />
                    </div>
                    <h2 className="text-sm font-semibold">等待实时文字</h2>
                    <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">
                      {asrProvider === "mock"
                        ? "当前ASR为模拟适配器，只能验证音频链路，不会识别真实语音。"
                        : asrConfigured
                          ? audioActive
                            ? "正在连接直播音频，阿里云识别结果将在这里持续追加。"
                            : "在直播标签页启动浏览器扩展，识别结果将在这里持续追加。"
                          : "阿里云实时语音识别尚未完成密钥配置，采集启动前请先配置服务器环境变量。"}
                    </p>
                  </div>
                ) : (
                  <ol className="divide-y divide-border/60">
                    {transcripts.map((item) => (
                      <li
                        key={item.id}
                        className="grid grid-cols-[58px_minmax(0,1fr)] gap-3 px-4 py-3 transition-colors hover:bg-muted/35"
                      >
                        <time className="pt-0.5 text-xs tabular-nums text-muted-foreground">
                          {formatDuration(Math.floor(item.start_ms / 1000))}
                        </time>
                        <p className="text-sm leading-6">{item.text}</p>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </CardContent>
          </Card>

          <div className="grid content-start gap-4 sm:grid-cols-2 xl:grid-cols-1">
            <Card className="bg-card/80">
              <CardHeader className="border-b border-border/60">
                <CardTitle>场次信息</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm">
                <InfoRow
                  label="创建时间"
                  value={formatDateTime(session.created_at)}
                />
                <InfoRow
                  label="开始时间"
                  value={formatDateTime(session.started_at)}
                />
                <InfoRow
                  label="结束时间"
                  value={formatDateTime(session.ended_at)}
                />
                <InfoRow
                  label="直播链接"
                  value={session.live_url ? "已关联" : "未填写"}
                />
                <InfoRow label="场次ID" value={session.id.slice(0, 8)} mono />
              </CardContent>
            </Card>

            <Card className="bg-card/80">
              <CardHeader className="border-b border-border/60">
                <CardTitle>录音文件</CardTitle>
                <CardDescription>
                  链接监听或采集助手停止后，WAV文件会完成封装。
                </CardDescription>
              </CardHeader>
              <CardContent>
                {session.audio_path ? (
                  <audio
                    className="h-9 w-full"
                    controls
                    crossOrigin="use-credentials"
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

            {(asrProvider === "mock" || !asrConfigured) && (
              <Alert className="grid gap-2 border-warning/40 bg-warning/8">
                <div className="flex items-center gap-2 font-medium">
                  <TriangleAlert className="size-4 text-warning" />
                  {asrProvider === "mock" ? "模拟识别模式" : "配置未完成"}
                </div>
                <p className="text-xs leading-5 text-muted-foreground">
                  {asrProvider === "mock"
                    ? "当前模拟ASR只验证传输链路，不会显示主播实际讲话内容。"
                    : "请在服务器配置阿里云AppKey和RAM用户AccessKey，重启后端后生效。"}
                </p>
              </Alert>
            )}
          </div>
        </div>

        <AiDashboard
          metrics={metrics}
          metricAt={latestMetricAt}
          insight={insight}
          llmConfigured={llmConfigured}
          llmModel={llmModel}
        />
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
    <Card className="bg-card/85">
      <CardContent className="flex items-center gap-3.5 p-4">
        <div
          className={cn(
            "flex size-10 items-center justify-center rounded-xl bg-muted text-muted-foreground ring-1 ring-inset ring-border/50",
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
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <p className="mt-1 text-sm font-semibold tabular-nums tracking-tight">{value}</p>
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
    <div className="flex items-center justify-between gap-4 border-b border-border/50 pb-2.5 last:border-0 last:pb-0">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("truncate text-right", mono && "font-mono text-xs")}>
        {value}
      </span>
    </div>
  )
}
