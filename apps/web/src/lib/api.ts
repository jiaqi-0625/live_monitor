import type {
  AiConfig,
  AiConfigInput,
  AiConfigProbe,
  AiConfigPurpose,
  AudioSourceStatus,
  CorpusEntry,
  CorpusEntryInput,
  CorpusImportResult,
  HealthStatus,
  LiveDashboard,
  MultiRoomOverview,
  LiveSession,
  LiveSourceProbeResult,
  LoginInput,
  RegisterInput,
  SessionCreateInput,
  SessionDetail,
  SessionReview,
  UserAdminUpdate,
  UserProfile,
} from "@/types"

const localHost = window.location.hostname || "127.0.0.1"
const defaultApiBase = import.meta.env.DEV
  ? `http://${localHost}:8000`
  : window.location.origin
const websocketProtocol = window.location.protocol === "https:" ? "wss:" : "ws:"
const defaultWsBase = import.meta.env.DEV
  ? `ws://${localHost}:8000`
  : `${websocketProtocol}//${window.location.host}`

export const API_BASE =
  import.meta.env.VITE_API_BASE ?? defaultApiBase
export const WS_BASE =
  import.meta.env.VITE_WS_BASE ?? defaultWsBase

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

function errorMessage(payload: unknown, status: number) {
  if (status === 413) {
    return "上传内容超过服务器限制，请减少文件数量或压缩文件后重试"
  }
  if (!payload || typeof payload !== "object" || !("detail" in payload)) {
    return `请求失败（${status}）`
  }
  const detail = payload.detail
  if (typeof detail === "string") return detail
  if (!Array.isArray(detail) || detail.length === 0) return `请求失败（${status}）`

  const issue = detail[0] as {
    type?: string
    loc?: Array<string | number>
    msg?: string
    ctx?: Record<string, number>
  }
  const field = String(issue.loc?.at(-1) ?? "输入内容")
  const fieldName = {
    username: "用户名",
    display_name: "显示姓名",
    password: "密码",
  }[field] ?? field
  if (issue.type === "string_too_short") {
    return `${fieldName}至少需要 ${issue.ctx?.min_length ?? "规定"} 个字符`
  }
  if (issue.type === "string_too_long") {
    return `${fieldName}不能超过 ${issue.ctx?.max_length ?? "规定"} 个字符`
  }
  if (issue.type === "string_pattern_mismatch") {
    return `${fieldName}只能包含中文、字母、数字、点、下划线或短横线`
  }
  return issue.msg?.replace(/^Value error,\s*/, "") ?? `${fieldName}格式不正确`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase()
  const maxAttempts = method === "GET" ? 2 : 1
  let response: Response | null = null

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      response = await fetch(`${API_BASE}${path}`, {
        ...init,
        credentials: "include",
        headers: {
          ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
          ...init?.headers,
        },
      })
      break
    } catch {
      if (attempt + 1 < maxAttempts) {
        await new Promise((resolve) => window.setTimeout(resolve, 500))
      }
    }
  }

  if (!response) {
    throw new Error("无法连接服务，请检查网络后重试")
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new ApiError(errorMessage(detail, response.status), response.status)
  }
  return response.json() as Promise<T>
}

export function register(payload: RegisterInput) {
  return request<UserProfile>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function login(payload: LoginInput) {
  return request<UserProfile>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function logout() {
  return request<{ logged_out: boolean }>("/api/auth/logout", { method: "POST" })
}

export function getCurrentUser() {
  return request<UserProfile>("/api/auth/me")
}

export function listUsers() {
  return request<UserProfile[]>("/api/admin/users")
}

export function updateUser(userId: string, payload: UserAdminUpdate) {
  return request<UserProfile>(`/api/admin/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })
}

export function listAiConfigs() {
  return request<AiConfig[]>("/api/admin/ai-configs")
}

export function updateAiConfig(purpose: AiConfigPurpose, payload: AiConfigInput) {
  return request<AiConfig>(`/api/admin/ai-configs/${purpose}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export function listAiModels(purpose: AiConfigPurpose, payload: AiConfigProbe) {
  return request<{ models: string[] }>(`/api/admin/ai-configs/${purpose}/models`, {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function testAiConfig(purpose: AiConfigPurpose, payload: AiConfigProbe) {
  return request<{ success: boolean; message: string }>(
    `/api/admin/ai-configs/${purpose}/test`,
    { method: "POST", body: JSON.stringify(payload) },
  )
}

export function getHealth() {
  return request<HealthStatus>("/api/health")
}

export function listSessions() {
  return request<LiveSession[]>("/api/sessions")
}

export function getSession(sessionId: string) {
  return request<SessionDetail>(`/api/sessions/${sessionId}`)
}

export function getLiveDashboard(sessionId: string) {
  return request<LiveDashboard>(`/api/sessions/${sessionId}/dashboard`)
}

export function getMultiRoomOverview(operatorName: string) {
  const query = new URLSearchParams({ operator_name: operatorName })
  return request<MultiRoomOverview>(`/api/overview?${query.toString()}`)
}

export function createSession(payload: SessionCreateInput) {
  return request<LiveSession>("/api/sessions", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function endSession(sessionId: string) {
  return request<LiveSession>(`/api/sessions/${sessionId}/end`, {
    method: "POST",
  })
}

export function getSessionReview(sessionId: string) {
  return request<SessionReview | null>(`/api/sessions/${sessionId}/review`)
}

export function generateSessionReview(sessionId: string) {
  return request<{ status: "pending" }>(
    `/api/sessions/${sessionId}/review/generate`,
    { method: "POST" },
  )
}

export function listCorpus(operatorName: string) {
  const query = new URLSearchParams({ operator_name: operatorName })
  return request<CorpusEntry[]>(`/api/corpus?${query.toString()}`)
}

export function createCorpusEntry(payload: CorpusEntryInput) {
  return request<CorpusEntry>("/api/corpus", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function importCorpusFiles(
  operatorName: string,
  category: string,
  files: File[],
  onProgress?: (progress: CorpusImportProgress) => void,
) {
  const formData = new FormData()
  formData.append("operator_name", operatorName)
  formData.append("category", category)
  files.forEach((file) => formData.append("files", file))

  return new Promise<CorpusImportResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("POST", `${API_BASE}/api/corpus/import`)
    xhr.withCredentials = true

    xhr.upload.onprogress = (event) => {
      const percent = event.lengthComputable && event.total > 0
        ? Math.min(100, Math.round((event.loaded / event.total) * 100))
        : null
      onProgress?.({ phase: "uploading", percent })
    }
    xhr.upload.onload = () => {
      onProgress?.({ phase: "processing", percent: 100 })
    }
    xhr.onerror = () => reject(new Error("无法连接服务，请检查网络后重试"))
    xhr.onabort = () => reject(new Error("文件导入已取消"))
    xhr.onload = () => {
      let payload: unknown = null
      try {
        payload = xhr.responseText ? JSON.parse(xhr.responseText) : null
      } catch {
        // Non-JSON proxy errors are converted to a useful status message below.
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(new ApiError(errorMessage(payload, xhr.status), xhr.status))
        return
      }
      if (!payload || typeof payload !== "object") {
        reject(new Error("服务返回内容无法识别，请稍后重试"))
        return
      }
      resolve(payload as CorpusImportResult)
    }
    xhr.send(formData)
  })
}

export interface CorpusImportProgress {
  phase: "uploading" | "processing"
  percent: number | null
}

export function updateCorpusEntry(
  entryId: number,
  payload: Partial<CorpusEntryInput> & { operator_name: string },
) {
  return request<CorpusEntry>(`/api/corpus/${entryId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export function deleteCorpusEntry(entryId: number, operatorName: string) {
  const query = new URLSearchParams({ operator_name: operatorName })
  return request<{ deleted: boolean }>(
    `/api/corpus/${entryId}?${query.toString()}`,
    { method: "DELETE" },
  )
}

export function probeLiveSource(sessionId: string) {
  return request<LiveSourceProbeResult>(
    `/api/sessions/${sessionId}/live-source/probe`,
    { method: "POST" },
  )
}

export function startLiveSource(sessionId: string) {
  return request<AudioSourceStatus>(
    `/api/sessions/${sessionId}/live-source/start`,
    { method: "POST" },
  )
}

export function stopLiveSource(sessionId: string) {
  return request<AudioSourceStatus>(
    `/api/sessions/${sessionId}/live-source/stop`,
    { method: "POST" },
  )
}

export function audioUrl(sessionId: string) {
  return `${API_BASE}/api/sessions/${sessionId}/audio`
}
