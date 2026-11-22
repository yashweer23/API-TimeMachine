export type Json =
  | null
  | boolean
  | number
  | string
  | Json[]
  | { [key: string]: Json };
export interface Project {
  id: string;
  name: string;
  description: string | null;
  base_url: string;
  created_at: string;
  updated_at: string;
}
export interface RecordingSummary {
  id: string;
  project_id: string;
  name: string;
  method: string;
  endpoint_path: string;
  response_status: number | null;
  duration_ms: number;
  captured_at: string;
  environment_label: string | null;
  is_baseline: boolean;
  execution_error: { code: string; message: string } | null;
}
export interface Recording extends RecordingSummary {
  base_url: string;
  query_parameters: Record<string, string | string[]>;
  request_headers: Record<string, string>;
  request_body: Json;
  request_body_present: boolean | null;
  response_headers: Record<string, string | string[]>;
  response_body: Json;
  response_body_kind: string;
  content_type: string | null;
}
export interface RecordingPage {
  items: RecordingSummary[];
  total: number;
  limit: number;
  offset: number;
}
export interface SendPayload {
  method: string;
  endpoint_path: string;
  headers: Record<string, string>;
  query_parameters: Record<string, string | string[]>;
  body?: Json;
  name?: string;
  environment_label?: string;
}
