import { useCallback, useEffect, useState } from "react"
import {
  Activity,
  AudioWaveform,
  History,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Sun,
  UserRound,
  X,
} from "lucide-react"

import { CreateSessionForm } from "@/components/create-session-form"
import { LiveMonitor } from "@/components/live-monitor"
import { SessionList } from "@/components/session-list"
import { Alert } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  createSession,
  getSession,
  listSessions,
} from "@/lib/api"
import { cn } from "@/lib/utils"
import type {
  LiveSession,
  SessionCreateInput,
  SessionDetail,
} from "@/types"

export default function App() {
  const [sessions, setSessions] = useState<LiveSession[]>([])
  const [activeSession, setActiveSession] = useState<SessionDetail | null>(null)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [createPanelOpen, setCreatePanelOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(
    () => window.matchMedia("(min-width: 1024px)").matches,
  )
  const [error, setError] = useState<string | null>(null)
  const [darkMode, setDarkMode] = useState(false)
  const [operatorName, setOperatorName] = useState(
    () => localStorage.getItem("operatorName") ?? "内部优化师",
  )

  const refreshSessions = useCallback(async () => {
    const items = await listSessions()
    setSessions(items)
    return items
  }, [])

  const selectSession = useCallback(async (sessionId: string) => {
    setActiveId(sessionId)
    const detail = await getSession(sessionId)
    setActiveSession(detail)
  }, [])

  const refreshActive = useCallback(async () => {
    await refreshSessions()
    if (activeId) {
      await selectSession(activeId)
    }
  }, [activeId, refreshSessions, selectSession])

  useEffect(() => {
    async function load() {
      try {
        const items = await refreshSessions()
        if (items.length > 0) {
          await selectSession(items[0].id)
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "无法连接后端服务")
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [refreshSessions, selectSession])

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode)
  }, [darkMode])

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 1024px)")
    const syncSidebar = () => setSidebarOpen(desktop.matches)
    syncSidebar()
    desktop.addEventListener("change", syncSidebar)
    return () => desktop.removeEventListener("change", syncSidebar)
  }, [])

  async function handleCreate(input: SessionCreateInput) {
    setCreating(true)
    setError(null)
    try {
      const created = await createSession(input)
      localStorage.setItem("operatorName", input.operator_name)
      setOperatorName(input.operator_name)
      await refreshSessions()
      await selectSession(created.id)
      setCreatePanelOpen(false)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建场次失败")
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="flex min-h-screen bg-background">
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-20 flex w-72 flex-col bg-sidebar text-sidebar-foreground transition-transform lg:static",
          !sidebarOpen && "-translate-x-full lg:w-0",
        )}
      >
        <div className="flex h-16 items-center gap-3 border-b border-white/10 px-4">
          <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <AudioWaveform className="size-5" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">汽车直播智能辅助</p>
            <p className="text-xs text-sidebar-muted">盯播工作台 · 内部试点</p>
          </div>
          <Button
            className="ml-auto text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground"
            variant="ghost"
            size="icon"
            onClick={() => setSidebarOpen(false)}
            aria-label="收起侧边栏"
          >
            <PanelLeftClose />
          </Button>
        </div>

        <nav className="grid gap-1 px-3 py-3" aria-label="主导航">
          <div className="flex items-center gap-2 rounded-md bg-sidebar-accent px-3 py-2 text-sm font-medium">
            <Activity className="size-4" />
            实时盯播
          </div>
          <div className="flex items-center gap-2 px-3 py-2 text-sm text-sidebar-muted">
            <History className="size-4" />
            历史场次
          </div>
        </nav>

        <div className="flex items-center justify-between px-4 pb-2 pt-1">
          <p className="text-xs font-medium uppercase tracking-wider text-sidebar-muted">
            最近场次
          </p>
          <Button
            variant="ghost"
            size="icon"
            className="size-7 text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground"
            onClick={() => setCreatePanelOpen(true)}
            aria-label="新建场次"
          >
            <Plus />
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto pb-4">
          <SessionList
            sessions={sessions}
            activeId={activeId}
            loading={loading}
            onSelect={(id) => void selectSession(id)}
          />
        </div>

        <div className="border-t border-white/10 p-3">
          <div className="flex items-center gap-3 rounded-lg px-2 py-2">
            <div className="flex size-8 items-center justify-center rounded-md bg-sidebar-accent">
              <UserRound className="size-4" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{operatorName}</p>
              <p className="text-xs text-sidebar-muted">盯播优化师</p>
            </div>
          </div>
        </div>
      </aside>

      {sidebarOpen && (
        <button
          type="button"
          className="fixed inset-0 z-10 bg-foreground/30 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-label="关闭侧边栏遮罩"
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center gap-3 border-b bg-card px-4 lg:px-6">
          {!sidebarOpen && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(true)}
              aria-label="展开侧边栏"
            >
              <PanelLeftOpen />
            </Button>
          )}
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">实时盯播</p>
            <p className="text-xs text-muted-foreground">
              抖音 · 懂车云店
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setDarkMode((current) => !current)}
            aria-label={darkMode ? "切换浅色模式" : "切换深色模式"}
          >
            {darkMode ? <Sun /> : <Moon />}
          </Button>
          <Button onClick={() => setCreatePanelOpen(true)}>
            <Plus data-icon="inline-start" />
            新建场次
          </Button>
        </header>

        <main className="min-h-0 flex-1 p-4 lg:p-6">
          {error && (
            <Alert className="mb-4 flex items-center justify-between gap-4 border-destructive/40 bg-destructive/5 text-destructive">
              <span>{error}</span>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setError(null)}
                aria-label="关闭错误提示"
              >
                <X />
              </Button>
            </Alert>
          )}

          {loading ? (
            <div className="grid gap-4">
              <div className="h-20 animate-pulse rounded-lg bg-muted" />
              <div className="grid gap-3 md:grid-cols-3">
                {[0, 1, 2].map((item) => (
                  <div
                    key={item}
                    className="h-16 animate-pulse rounded-lg bg-muted"
                  />
                ))}
              </div>
              <div className="h-[520px] animate-pulse rounded-lg bg-muted" />
            </div>
          ) : activeSession ? (
            <LiveMonitor
              session={activeSession}
              onRefresh={refreshActive}
            />
          ) : (
            <div className="flex min-h-[calc(100vh-9rem)] items-center justify-center">
              <Card className="w-full max-w-lg">
                <CardHeader className="items-center text-center">
                  <div className="mb-2 flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <AudioWaveform className="size-6" />
                  </div>
                  <CardTitle className="text-base">开始第一场实时盯播</CardTitle>
                  <CardDescription className="max-w-sm">
                    创建场次后，将场次ID复制到Windows采集助手，即可查看实时音频状态和转写结果。
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex justify-center">
                  <Button onClick={() => setCreatePanelOpen(true)}>
                    <Plus data-icon="inline-start" />
                    新建监控场次
                  </Button>
                </CardContent>
              </Card>
            </div>
          )}
        </main>
      </div>

      {createPanelOpen && (
        <div
          className="fixed inset-0 z-30 flex justify-end bg-foreground/30"
          role="presentation"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) setCreatePanelOpen(false)
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-session-title"
            className="h-full w-full max-w-md overflow-y-auto border-l bg-background p-4 shadow-xl"
          >
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 id="create-session-title" className="font-semibold">
                  创建监控场次
                </h2>
                <p className="text-sm text-muted-foreground">
                  为Windows采集助手生成新的场次ID。
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setCreatePanelOpen(false)}
                aria-label="关闭创建场次"
              >
                <X />
              </Button>
            </div>

            <div className="mb-4 grid gap-2">
              <label
                htmlFor="operator-name"
                className="text-sm font-medium"
              >
                优化师姓名
              </label>
              <Input
                id="operator-name"
                value={operatorName}
                onChange={(event) => setOperatorName(event.target.value)}
              />
            </div>

            <CreateSessionForm
              operatorName={operatorName}
              pending={creating}
              onCreate={handleCreate}
            />
          </section>
        </div>
      )}
    </div>
  )
}
