import type { Json, Recording } from "./index";
export interface ReplayConfig {
  sample_v2_base_url?: string | null;
  allowed_target_origins: string[];
  max_batch_size: number;
  session_timeout_seconds: number;
  execution_mode: string;
}
export interface ReplayOverride {
  headers?: Record<string, string | null>;
  query_parameters?: Record<string, string | string[]>;
  body?: Json;
  omit_body?: boolean;
}
export interface ReplayPayload {
  name: string;
  target_base_url: string;
  recording_ids: string[];
  temporary_headers: Record<string, string>;
  overrides: Record<string, ReplayOverride>;
  confirm_side_effects: boolean;
}
export interface ReplaySession {
  id: string;
  project_id: string;
  name: string;
  target_base_url: string;
  status: string;
  total_requests: number;
  completed_requests: number;
  failed_requests: number;
  error_requests: number;
  http_responses: number;
  skipped_requests: number;
  started_at: string;
  completed_at: string | null;
  duration_ms: number;
}
export interface ReplayResultSummary {
  id: string;
  replay_session_id: string;
  original_recording_id: string;
  ordinal: number;
  request_method: string;
  endpoint_path: string;
  replay_url: string;
  outcome: string;
  response_status: number | null;
  duration_ms: number;
  execution_error: { code: string; message: string } | null;
  executed_at: string | null;
}
export interface ReplayResult extends ReplayResultSummary {
  request_metadata: {
    headers: Record<string, string>;
    query_parameters: Record<string, string | string[]>;
    body: Json;
    body_present: boolean;
  };
  response_headers: Record<string, string | string[]>;
  response_body: Json;
  response_body_kind: string;
  content_type: string | null;
  original_recording: Recording;
}
export interface ReplaySessionDetail extends ReplaySession {
  results: ReplayResultSummary[];
}
export interface ReplaySessionPage {
  items: ReplaySession[];
  total: number;
  limit: number;
  offset: number;
}
export interface ReplayDraft {
  headers: string;
  query: string;
  bodyMode: "keep" | "replace" | "omit";
  body: string;
}
export const emptyDraft = (): ReplayDraft => ({
  headers: "",
  query: "",
  bodyMode: "keep",
  body: "",
});
