import { useCallback, useEffect, useState } from "react"
import {
  CheckCircle2,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  UserCog,
  UserRoundX,
  UsersRound,
} from "lucide-react"

import { AdminAiConfig } from "@/components/admin-ai-config"
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
import { listUsers, updateUser } from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import type { UserProfile, UserRole, UserStatus } from "@/types"

interface AdminUsersProps {
  currentUser: UserProfile
  onCurrentUserChanged: (user: UserProfile) => void
}

const statusLabels: Record<UserStatus, string> = {
  pending: "待审核",
  active: "已启用",
  disabled: "已停用",
}

const statusVariants = {
  pending: "warning",
  active: "success",
  disabled: "destructive",
} as const

export function AdminUsersView({
  currentUser,
  onCurrentUserChanged,
}: AdminUsersProps) {
  const [users, setUsers] = useState<UserProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [updatingId, setUpdatingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadUsers = useCallback(async () => {
    setLoading(true)
    try {
      setUsers(await listUsers())
      setError(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "用户列表加载失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadUsers()
  }, [loadUsers])

  useEffect(() => {
    const refreshTimer = window.setInterval(() => {
      void listUsers().then(setUsers).catch(() => undefined)
    }, 15_000)
    return () => window.clearInterval(refreshTimer)
  }, [])

  async function changeUser(
    user: UserProfile,
    changes: { role?: UserRole; status?: UserStatus },
  ) {
    if (
      changes.status === "disabled" &&
      !window.confirm(`确定停用“${user.display_name}”吗？该用户将立即无法访问控制台。`)
    ) {
      return
    }
    setUpdatingId(user.id)
    setError(null)
    try {
      const updated = await updateUser(user.id, changes)
      setUsers((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      )
      if (updated.id === currentUser.id) onCurrentUserChanged(updated)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "账号更新失败")
    } finally {
      setUpdatingId(null)
    }
  }

  const pendingCount = users.filter((user) => user.status === "pending").length
  const activeCount = users.filter((user) => user.status === "active").length
  const adminCount = users.filter((user) => user.role === "admin").length

  return (
    <section className="grid gap-6" aria-labelledby="admin-users-title">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-primary">
            <span className="size-1.5 rounded-full bg-primary" />
            ACCESS CONTROL
          </div>
          <h1 id="admin-users-title" className="text-2xl font-semibold tracking-[-0.025em]">
            账号与权限管理
          </h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            审核注册申请、管理账号状态，并分配管理员或优化师权限。新申请每 15 秒自动刷新。
          </p>
        </div>
        <Button variant="outline" onClick={() => void loadUsers()} disabled={loading}>
          <RefreshCw data-icon="inline-start" className={loading ? "animate-spin" : ""} />
          刷新列表
        </Button>
      </div>

      {error && <Alert className="border-destructive/30 bg-destructive/5 text-destructive">{error}</Alert>}

      <AdminAiConfig />

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          { icon: UsersRound, label: "账号总数", value: users.length },
          { icon: CheckCircle2, label: "启用账号", value: activeCount },
          { icon: UserCog, label: "待审核", value: pendingCount },
        ].map(({ icon: Icon, label, value }) => (
          <Card key={label} className="bg-card/90">
            <CardContent className="flex items-center gap-4 p-4">
              <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Icon className="size-5" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="overflow-hidden bg-card/90">
        <CardHeader className="border-b border-border/60">
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-primary" />
            用户列表
          </CardTitle>
          <CardDescription>
            当前共有 {adminCount} 名管理员。系统始终要求至少保留一名启用中的管理员。
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="grid gap-3 p-5">
              {[0, 1, 2].map((item) => (
                <div key={item} className="h-16 animate-pulse rounded-xl bg-muted" />
              ))}
            </div>
          ) : users.length === 0 ? (
            <div className="grid min-h-60 place-items-center text-center">
              <div>
                <UsersRound className="mx-auto size-9 text-muted-foreground" />
                <p className="mt-3 text-sm font-medium">暂无用户</p>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] border-collapse text-left text-sm">
                <thead className="bg-muted/45 text-xs text-muted-foreground">
                  <tr>
                    <th className="px-5 py-3 font-medium">用户</th>
                    <th className="px-4 py-3 font-medium">状态</th>
                    <th className="px-4 py-3 font-medium">角色</th>
                    <th className="px-4 py-3 font-medium">注册时间</th>
                    <th className="px-5 py-3 text-right font-medium">账号操作</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => {
                    const isUpdating = updatingId === user.id
                    return (
                      <tr key={user.id} className="border-t border-border/60 hover:bg-muted/25">
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-3">
                            <div className="flex size-9 items-center justify-center rounded-lg bg-secondary font-semibold text-secondary-foreground">
                              {user.display_name.slice(0, 1).toUpperCase()}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="max-w-44 truncate font-medium">{user.display_name}</p>
                                {user.id === currentUser.id && <Badge variant="outline">当前账号</Badge>}
                              </div>
                              <p className="mt-0.5 max-w-52 truncate text-xs text-muted-foreground">
                                @{user.username}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <Badge variant={statusVariants[user.status]}>
                            {statusLabels[user.status]}
                          </Badge>
                        </td>
                        <td className="px-4 py-4">
                          <label className="sr-only" htmlFor={`role-${user.id}`}>用户角色</label>
                          <select
                            id={`role-${user.id}`}
                            value={user.role}
                            disabled={isUpdating}
                            onChange={(event) =>
                              void changeUser(user, { role: event.target.value as UserRole })
                            }
                            className="h-9 rounded-lg border border-input bg-card px-3 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            <option value="operator">优化师</option>
                            <option value="admin">管理员</option>
                          </select>
                        </td>
                        <td className="px-4 py-4 text-xs text-muted-foreground">
                          {formatDateTime(user.created_at)}
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex justify-end gap-2">
                            {isUpdating ? (
                              <Button variant="ghost" size="sm" disabled>
                                <LoaderCircle className="animate-spin" />
                                更新中
                              </Button>
                            ) : user.status === "active" ? (
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-destructive hover:text-destructive"
                                onClick={() => void changeUser(user, { status: "disabled" })}
                              >
                                <UserRoundX data-icon="inline-start" />
                                停用
                              </Button>
                            ) : (
                              <Button
                                size="sm"
                                onClick={() => void changeUser(user, { status: "active" })}
                              >
                                <CheckCircle2 data-icon="inline-start" />
                                {user.status === "pending" ? "通过审核" : "重新启用"}
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
