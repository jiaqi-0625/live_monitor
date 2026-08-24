export type Platform = "douyin" | "dongchedi"
export type SessionStatus = "created" | "live" | "ended" | "failed"
export type UserRole = "admin" | "operator"
export type UserStatus = "pending" | "active" | "disabled"

export interface UserProfile {
  id: string
  username: string
  display_name: string
  role: UserRole
  status: UserStatus
  created_at: string
  updated_at: string
  last_login_at: string | null
}

export interface RegisterInput {
  username: string
  display_name: string
  password: string
}

export interface LoginInput {
  username: string
  password: string
}

export interface UserAdminUpdate {
  display_name?: string
  role?: UserRole
  status?: UserStatus
}

export type AiConfigPurpose = "realtime" | "corpus"

export interface AiConfig {
  purpose: AiConfigPurpose
  api_base: string
  model: string
  configured: boolean
  has_api_key: boolean
  source: "admin" | "environment"
  updated_at: string | null
}

export interface AiConfigInput {
  api_base: string
  api_key?: string
  model: string
}

export interface AiConfigProbe {
  api_base: string
  api_key?: string
  model?: string
}

export interface TranscriptItem {
  id: number
  session_id: string
  text: string
  start_ms: number
  end_ms: number
  is_final: boolean
  created_at: string
}

export interface LiveSession {
  id: string
  title: string
  platform: Platform
  operator_name: string
  room_name: string
  live_url: string
  status: SessionStatus
  created_at: string
  started_at: string | null
  ended_at: string | null
  duration_seconds: number
  audio_path: string | null
  transcript_count: number
}

export interface SessionDetail extends LiveSession {
  transcripts: TranscriptItem[]
}

export interface SessionCreateInput {
  title: string
  platform: Platform
  operator_name: string
  room_name: string
  live_url: string
}

export interface HealthStatus {
  status: string
  environment: string
  asr_provider: string
  asr_configured: boolean
  llm_model: string
  llm_configured: boolean
}

export interface LiveSourceProbeResult {
  status: "live" | "offline" | "unsupported" | "error"
  message: string
  qualities: string[]
  room_id: string | null
  title: string | null
  author: string | null
}

export interface AudioSourceStatus {
  active: boolean
  connected: boolean
  source: "windows" | "browser_extension" | "live_url" | null
  message: string
}

export interface MetricSnapshot {
  id: number
  session_id: string
  endpoint: string
  normalized: Record<string, number>
  captured_at: string
  created_at: string
}

export interface AiInsight {
  id: number
  session_id: string
  risk_level: "normal" | "attention" | "critical"
  summary: string
  signals: string[]
  actions: string[]
  talk_track: string
  model: string
  created_at: string
}

export interface LiveDashboard {
  latest_metrics: Record<string, number>
  latest_metric_at: string | null
  latest_insight: AiInsight | null
}

export interface LiveRoomOverview {
  session: LiveSession
  dashboard: LiveDashboard
}

export interface MultiRoomOverview {
  rooms: LiveRoomOverview[]
  updated_at: string
}

export type ReviewStatus = "pending" | "completed" | "failed"

export interface SessionReview {
  id: number
  session_id: string
  status: ReviewStatus
  summary: string
  metric_summary: string
  highlights: string[]
  issues: string[]
  actions: string[]
  key_metrics: Record<string, number>
  model: string
  error: string
  created_at: string
  updated_at: string
}

export interface CorpusEntry {
  id: number
  operator_name: string
  category: string
  title: string
  content: string
  enabled: boolean
  source_name: string | null
  source_type: string | null
  created_at: string
  updated_at: string
}

export interface CorpusEntryInput {
  operator_name: string
  category: string
  title: string
  content: string
  enabled?: boolean
}

export interface CorpusImportResult {
  imported_files: number
  imported_entries: number
  original_chars: number
  saved_chars: number
  fallback_files: string[]
  entries: CorpusEntry[]
  failures: Array<{ filename: string; error: string }>
}

export interface MonitorEvent {
  type:
    | "session"
    | "audio_status"
    | "transcript"
    | "metrics"
    | "ai_insight"
    | "warning"
    | "heartbeat"
  payload: Record<string, unknown>
}

