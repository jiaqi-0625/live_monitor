import type {
  LiveSession,
  SessionCreateInput,
  SessionDetail,
} from "@/types"

const localHost = window.location.hostname || "127.0.0.1"

export const API_BASE =
  import.meta.env.VITE_API_BASE ?? `http://${localHost}:8000`
export const WS_BASE =
  import.meta.env.VITE_WS_BASE ?? `ws://${localHost}:8000`

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

export function listSessions() {
  return request<LiveSession[]>("/api/sessions")
}

export function getSession(sessionId: string) {
  return request<SessionDetail>(`/api/sessions/${sessionId}`)
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

export function audioUrl(sessionId: string) {
  return `${API_BASE}/api/sessions/${sessionId}/audio`
}
