export type Platform = "douyin" | "dongchedi"
export type SessionStatus = "created" | "live" | "ended" | "failed"

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
}

export interface MonitorEvent {
  type: "session" | "audio_status" | "transcript" | "warning" | "heartbeat"
  payload: Record<string, unknown>
}

