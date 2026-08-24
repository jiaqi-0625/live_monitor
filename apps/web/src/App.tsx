import { useCallback, useEffect, useState } from "react"
import {
  AudioWaveform,
  BookOpenText,
  History,
  LayoutDashboard,
  LogOut,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  RotateCcw,
  ShieldCheck,
  Sun,
  UserRound,
  X,
} from "lucide-react"

import { AdminUsersView } from "@/components/admin-users"
import { AuthScreen } from "@/components/auth-screen"
import { CreateSessionForm } from "@/components/create-session-form"
import { CorpusLibraryView } from "@/components/corpus-library"
import { LiveMonitor } from "@/components/live-monitor"
import { MultiRoomOverviewView } from "@/components/multi-room-overview"
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
  getCurrentUser,
  getHealth,
  getSession,
  listSessions,
  logout,
} from "@/lib/api"
import { cn } from "@/lib/utils"
import type {
  LiveSession,
  SessionCreateInput,
  SessionDetail,
  UserProfile,
} from "@/types"

export default function App() {
  const [view, setView] = useState<"overview" | "session" | "corpus" | "admin">("overview")
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
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
  const [asrProvider, setAsrProvider] = useState("mock")
  const [asrConfigured, setAsrConfigured] = useState(true)
  const [llmConfigured, setLlmConfigured] = useState(false)
  const [llmModel, setLlmModel] = useState("deepseek-v4-flash")
  const operatorName = currentUser?.display_name ?? ""

  const refreshSessions = useCallback(async () => {
    const items = await listSessions()
    setSessions(items)
    return items
  }, [])

  const selectSession = useCallback(async (sessionId: string) => {
    setActiveId(sessionId)
    const detail = await getSession(sessionId)
    setActiveSession(detail)
    setView("session")
  }, [])

  const refreshActive = useCallback(async () => {
    await refreshSessions()
    if (activeId) {
      await selectSession(activeId)
    }
  }, [activeId, refreshSessions, selectSession])

  const loadInitialData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [items, health] = await Promise.all([
        refreshSessions(),
        getHealth(),
      ])
      setAsrProvider(health.asr_provider)
      setAsrConfigured(health.asr_configured)
      setLlmConfigured(health.llm_configured)
      setLlmModel(health.llm_model)
      if (items.length === 0) setActiveSession(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法连接后端服务")
    } finally {
      setLoading(false)
    }
  }, [refreshSessions])

  useEffect(() => {
    let cancelled = false
    getCurrentUser()
      .then((user) => {
        if (!cancelled) setCurrentUser(user)
      })
      .catch(() => {
        if (!cancelled) setCurrentUser(null)
      })
      .finally(() => {
        if (!cancelled) setAuthLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (currentUser) void loadInitialData()
  }, [currentUser, loadInitialData])

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
      await refreshSessions()
      await selectSession(created.id)
      setCreatePanelOpen(false)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建场次失败")
    } finally {
      setCreating(false)
    }
  }

  function handleAuthenticated(user: UserProfile) {
    setCurrentUser(user)
    setActiveId(null)
    setActiveSession(null)
    setView("overview")
    setError(null)
  }

  async function handleLogout() {
    try {
      await logout()
    } finally {
      setCurrentUser(null)
      setSessions([])
      setActiveId(null)
      setActiveSession(null)
      setView("overview")
    }
  }

  function handleCurrentUserChanged(user: UserProfile) {
    setCurrentUser(user)
    if (user.role !== "admin") setView("overview")
  }

  if (authLoading) {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <div className="grid justify-items-center gap-3 text-sm text-muted-foreground">
          <div className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <AudioWaveform className="size-5 animate-pulse" />
          </div>
          正在验证登录状态…
        </div>
      </div>
    )
  }

  if (!currentUser) {
    return <AuthScreen onAuthenticated={handleAuthenticated} />
  }

  return (
    <div className="flex min-h-screen bg-transparent">
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-20 flex w-[17rem] flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground shadow-2xl shadow-black/10 transition-[transform,width] duration-200 lg:sticky lg:top-0 lg:h-screen lg:shadow-none",
          !sidebarOpen && "-translate-x-full lg:w-0",
        )}
      >
        <div className="flex h-[4.5rem] shrink-0 items-center gap-3 border-b border-sidebar-border px-4">
          <div className="relative flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg shadow-primary/20 ring-1 ring-white/15">
            <AudioWaveform className="size-5" />
            <span className="absolute -right-0.5 -top-0.5 size-2.5 rounded-full border-2 border-sidebar bg-success" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold tracking-[-0.01em]">智播运营控制台</p>
            <p className="mt-0.5 text-[11px] tracking-wide text-sidebar-muted">LIVE INTELLIGENCE</p>
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

        <nav className="grid gap-1.5 px-3 py-4" aria-label="主导航">
          <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-sidebar-muted/70">
            工作空间
          </p>
          <button
            type="button"
            className={cn(
              "relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm outline-none transition-colors before:absolute before:bottom-2.5 before:left-0 before:top-2.5 before:w-0.5 before:rounded-full before:bg-primary before:opacity-0 hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-ring",
              view === "overview"
                ? "bg-sidebar-accent font-medium text-white before:opacity-100"
                : "text-sidebar-muted",
            )}
            onClick={() => setView("overview")}
          >
            <LayoutDashboard className="size-[18px]" />
            多直播间总览
          </button>
          <button
            type="button"
            className={cn(
              "relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm outline-none transition-colors before:absolute before:bottom-2.5 before:left-0 before:top-2.5 before:w-0.5 before:rounded-full before:bg-primary before:opacity-0 hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-ring",
              view === "corpus"
                ? "bg-sidebar-accent font-medium text-white before:opacity-100"
                : "text-sidebar-muted",
            )}
            onClick={() => setView("corpus")}
          >
            <BookOpenText className="size-[18px]" />
            我的语料库
          </button>
          {currentUser.role === "admin" && (
            <button
              type="button"
              className={cn(
                "relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm outline-none transition-colors before:absolute before:bottom-2.5 before:left-0 before:top-2.5 before:w-0.5 before:rounded-full before:bg-primary before:opacity-0 hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-ring",
                view === "admin"
                  ? "bg-sidebar-accent font-medium text-white before:opacity-100"
                  : "text-sidebar-muted",
              )}
              onClick={() => setView("admin")}
            >
              <ShieldCheck className="size-[18px]" />
              账号权限管理
            </button>
          )}
          <div className="flex items-center gap-3 px-3 py-2.5 text-sm text-sidebar-muted/70">
            <History className="size-[18px]" />
            历史场次
          </div>
        </nav>

        <div className="flex items-center justify-between border-t border-sidebar-border px-4 pb-2 pt-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-sidebar-muted/70">
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

        <div className="border-t border-sidebar-border p-3">
          <div className="flex items-center gap-3 rounded-xl bg-sidebar-accent/55 px-3 py-2.5 ring-1 ring-inset ring-sidebar-border">
            <div className="flex size-9 items-center justify-center rounded-lg bg-white/8 text-sidebar-foreground ring-1 ring-inset ring-white/8">
              <UserRound className="size-4" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{operatorName}</p>
              <p className="mt-0.5 text-[11px] text-sidebar-muted">
                {currentUser.role === "admin" ? "系统管理员" : "盯播优化师"}
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="mt-2 w-full justify-start text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground"
            onClick={() => void handleLogout()}
          >
            <LogOut data-icon="inline-start" />
            退出登录
          </Button>
        </div>
      </aside>

      {sidebarOpen && (
        <button
          type="button"
          className="fixed inset-0 z-10 bg-black/45 backdrop-blur-[2px] lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-label="关闭侧边栏遮罩"
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex h-[4.5rem] items-center gap-3 border-b border-border/70 bg-background/88 px-4 backdrop-blur-xl supports-[backdrop-filter]:bg-background/78 lg:px-7">
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
            <p className="text-[15px] font-semibold tracking-[-0.01em]">
              {view === "overview"
                ? "多直播间总览"
                : view === "corpus"
                  ? "我的语料库"
                  : view === "admin"
                    ? "账号权限管理"
                  : "实时盯播"}
            </p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              汽车直播实时运营中心
            </p>
          </div>
          <Button
            className="rounded-full"
            variant="ghost"
            size="icon"
            onClick={() => setDarkMode((current) => !current)}
            aria-label={darkMode ? "切换浅色模式" : "切换深色模式"}
          >
            {darkMode ? <Sun /> : <Moon />}
          </Button>
          {view !== "admin" && (
            <Button onClick={() => setCreatePanelOpen(true)}>
              <Plus data-icon="inline-start" />
              新建场次
            </Button>
          )}
        </header>

        <main className="min-h-0 flex-1 p-4 sm:p-5 lg:p-7">
          <div className="mx-auto w-full max-w-[1800px]">
          {error && (
            <Alert className="mb-4 flex items-center justify-between gap-4 border-destructive/40 bg-destructive/5 text-destructive">
              <span>{error}</span>
              <div className="flex shrink-0 items-center gap-1">
                <Button variant="ghost" size="sm" onClick={loadInitialData}>
                  <RotateCcw data-icon="inline-start" />
                  重新连接
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setError(null)}
                  aria-label="关闭错误提示"
                >
                  <X />
                </Button>
              </div>
            </Alert>
          )}

          {loading ? (
            <div className="grid gap-4">
              <div className="h-20 animate-pulse rounded-xl bg-muted" />
              <div className="grid gap-3 md:grid-cols-3">
                {[0, 1, 2].map((item) => (
                  <div
                    key={item}
                    className="h-16 animate-pulse rounded-xl bg-muted"
                  />
                ))}
              </div>
              <div className="h-[520px] animate-pulse rounded-xl bg-muted" />
            </div>
          ) : view === "overview" ? (
            <MultiRoomOverviewView
              operatorName={operatorName}
              onCreate={() => setCreatePanelOpen(true)}
              onSelect={(id) => void selectSession(id)}
            />
          ) : view === "corpus" ? (
            <CorpusLibraryView operatorName={operatorName} />
          ) : view === "admin" && currentUser.role === "admin" ? (
            <AdminUsersView
              currentUser={currentUser}
              onCurrentUserChanged={handleCurrentUserChanged}
            />
          ) : activeSession ? (
            <LiveMonitor
              session={activeSession}
              asrProvider={asrProvider}
              asrConfigured={asrConfigured}
              llmConfigured={llmConfigured}
              llmModel={llmModel}
              onRefresh={refreshActive}
            />
          ) : (
            <div className="flex min-h-[calc(100vh-9rem)] items-center justify-center">
              <Card className="w-full max-w-lg border-primary/15 bg-card/95">
                <CardHeader className="items-center text-center">
                  <div className="mb-2 flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-inset ring-primary/10">
                    <AudioWaveform className="size-6" />
                  </div>
                  <CardTitle className="text-base">开始第一场实时盯播</CardTitle>
                  <CardDescription className="max-w-sm">
                    创建场次后，将场次ID复制到浏览器扩展，即可查看实时音频、转写、大屏指标和AI建议。
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
          </div>
        </main>
      </div>

      {createPanelOpen && (
        <div
          className="fixed inset-0 z-30 flex justify-end bg-black/45 backdrop-blur-[2px]"
          role="presentation"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) setCreatePanelOpen(false)
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-session-title"
            className="h-full w-full max-w-md overflow-y-auto border-l border-border/70 bg-background p-5 shadow-2xl shadow-black/20 sm:p-6"
          >
            <div className="mb-6 flex items-start justify-between gap-4 border-b pb-5">
              <div>
                <h2 id="create-session-title" className="text-lg font-semibold tracking-tight">
                  创建监控场次
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  为浏览器扩展生成新的场次ID。
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

            <div className="mb-5 grid gap-2">
              <label
                htmlFor="operator-name"
                className="text-sm font-medium"
              >
                优化师姓名
              </label>
              <Input
                id="operator-name"
                value={operatorName}
                readOnly
                aria-readonly="true"
              />
              <p className="text-xs leading-5 text-muted-foreground">
                场次将自动归属当前登录账号，优化师姓名不可在此修改。
              </p>
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
