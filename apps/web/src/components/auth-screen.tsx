import { useState, type FormEvent } from "react"
import {
  AudioWaveform,
  CheckCircle2,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
  UserRoundPlus,
} from "lucide-react"

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
import { Label } from "@/components/ui/label"
import { login, register } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { UserProfile } from "@/types"

interface AuthScreenProps {
  onAuthenticated: (user: UserProfile) => void
}

export function AuthScreen({ onAuthenticated }: AuthScreenProps) {
  const [mode, setMode] = useState<"login" | "register">("login")
  const [username, setUsername] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [password, setPassword] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [registrationComplete, setRegistrationComplete] = useState(false)

  function changeMode(nextMode: "login" | "register") {
    setMode(nextMode)
    setError(null)
    setRegistrationComplete(false)
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    const normalizedUsername = username.trim()
    if (mode === "register") {
      if (!/^[A-Za-z0-9_.\-\u4e00-\u9fff]{2,40}$/u.test(normalizedUsername)) {
        setError("用户名需为 2–40 位，只能包含中文、字母、数字、点、下划线或短横线")
        return
      }
      if (password.length < 8) {
        setError("密码至少需要 8 个字符")
        return
      }
    }
    setPending(true)
    try {
      if (mode === "login") {
        onAuthenticated(await login({ username: normalizedUsername, password }))
        return
      }
      await register({
        username: normalizedUsername,
        display_name: displayName.trim(),
        password,
      })
      setRegistrationComplete(true)
      setPassword("")
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "操作失败，请稍后重试")
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="relative grid min-h-screen overflow-hidden bg-background lg:grid-cols-[minmax(0,1.1fr)_minmax(420px,0.9fr)]">
      <section className="relative hidden overflow-hidden border-r border-border/60 bg-sidebar p-12 text-sidebar-foreground lg:flex lg:flex-col lg:justify-between">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_25%_15%,color-mix(in_oklch,var(--primary)_25%,transparent),transparent_34rem)]" />
        <div className="relative flex items-center gap-3">
          <div className="flex size-11 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg shadow-primary/20">
            <AudioWaveform className="size-5" />
          </div>
          <div>
            <p className="font-semibold tracking-[-0.02em]">智播运营控制台</p>
            <p className="text-[11px] tracking-[0.16em] text-sidebar-muted">LIVE INTELLIGENCE</p>
          </div>
        </div>

        <div className="relative max-w-xl">
          <p className="mb-4 text-xs font-semibold uppercase tracking-[0.18em] text-primary">
            Secure workspace
          </p>
          <h1 className="text-4xl font-semibold leading-tight tracking-[-0.04em]">
            让每一位优化师，拥有独立而安全的直播工作台。
          </h1>
          <p className="mt-5 max-w-lg text-sm leading-7 text-sidebar-muted">
            登录后即可管理自己的直播场次、转写记录与个性化语料；管理员统一审核账号和配置权限。
          </p>
          <div className="mt-8 grid gap-3 sm:grid-cols-3">
            {[
              [LockKeyhole, "独立数据空间"],
              [ShieldCheck, "管理员审核"],
              [AudioWaveform, "采集能力保留"],
            ].map(([Icon, label]) => (
              <div
                key={label as string}
                className="flex items-center gap-2 rounded-xl border border-sidebar-border bg-sidebar-accent/55 px-3 py-3 text-xs text-sidebar-muted"
              >
                <Icon className="size-4 text-primary" />
                {label as string}
              </div>
            ))}
          </div>
        </div>

        <p className="relative text-xs text-sidebar-muted/70">汽车直播实时运营中心</p>
      </section>

      <section className="flex items-center justify-center p-5 sm:p-8 lg:p-12">
        <Card className="w-full max-w-md bg-card/95 shadow-[0_20px_60px_hsl(var(--shadow-color)/0.08)]">
          <CardHeader className="gap-2 border-b border-border/60 p-6">
            <div className="mb-2 flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-inset ring-primary/10 lg:hidden">
              <AudioWaveform className="size-5" />
            </div>
            <CardTitle className="text-xl">
              {mode === "login" ? "登录控制台" : "申请账号"}
            </CardTitle>
            <CardDescription className="text-sm">
              {mode === "login"
                ? "使用已通过审核的账号进入工作台。"
                : "提交后由管理员审核，通过后即可登录。"}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-6">
            <div className="mb-5 grid grid-cols-2 rounded-lg bg-muted p-1" aria-label="账号入口">
              {(["login", "register"] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  className={cn(
                    "rounded-md px-3 py-2 text-sm font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                    mode === item
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                  onClick={() => changeMode(item)}
                >
                  {item === "login" ? "登录" : "注册"}
                </button>
              ))}
            </div>

            {registrationComplete ? (
              <div className="grid gap-5 py-2 text-center">
                <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-success/12 text-success">
                  <CheckCircle2 className="size-6" />
                </div>
                <div>
                  <h2 className="font-semibold">账号申请已提交</h2>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    请等待管理员审核。审核通过后，使用刚才的用户名和密码登录。
                  </p>
                </div>
                <Button variant="outline" onClick={() => changeMode("login")}>
                  返回登录
                </Button>
              </div>
            ) : (
              <form className="grid gap-4" onSubmit={handleSubmit}>
                {error && <Alert className="border-destructive/30 bg-destructive/5 text-destructive">{error}</Alert>}

                <div className="grid gap-2">
                  <Label htmlFor="auth-username">用户名</Label>
                  <Input
                    id="auth-username"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    autoComplete="username"
                    placeholder="2–40 位中文、字母、数字或 . _ -"
                    minLength={2}
                    maxLength={40}
                    required
                  />
                </div>

                {mode === "register" && (
                  <div className="grid gap-2">
                    <Label htmlFor="auth-display-name">显示姓名</Label>
                    <Input
                      id="auth-display-name"
                      value={displayName}
                      onChange={(event) => setDisplayName(event.target.value)}
                      autoComplete="name"
                      placeholder="例如：优化师小李"
                      maxLength={40}
                      required
                    />
                  </div>
                )}

                <div className="grid gap-2">
                  <Label htmlFor="auth-password">密码</Label>
                  <Input
                    id="auth-password"
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                    placeholder={mode === "register" ? "至少 8 个字符" : "请输入密码"}
                    minLength={mode === "register" ? 8 : 1}
                    maxLength={128}
                    required
                  />
                </div>

                <Button className="mt-1 w-full" size="lg" type="submit" disabled={pending}>
                  {pending ? (
                    <LoaderCircle className="animate-spin" />
                  ) : mode === "login" ? (
                    <LockKeyhole data-icon="inline-start" />
                  ) : (
                    <UserRoundPlus data-icon="inline-start" />
                  )}
                  {pending ? "请稍候" : mode === "login" ? "登录控制台" : "提交注册申请"}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      </section>
    </main>
  )
}
