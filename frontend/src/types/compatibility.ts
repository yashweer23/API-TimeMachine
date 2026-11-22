import type { ComparisonRules } from "./comparison";
import type { Json } from "./index";
export type Classification =
  | "confirmed_breaking"
  | "potentially_breaking"
  | "informational"
  | "unassessed";
export type Severity = "critical" | "high" | "medium" | "low";
export interface EndpointPolicy {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  endpoint_path: string;
  expected_status_codes: number[];
  required_json_paths: string[];
  expected_types: Record<
    string,
    "object" | "array" | "string" | "number" | "integer" | "boolean" | "null"
  >;
  required_headers: string[];
  allowed_content_types: string[];
  allow_additional_fields: boolean | null;
  dynamic_json_paths: string[];
}
export interface PolicyBundle {
  endpoints: EndpointPolicy[];
}
export interface PolicySettings {
  project_id: string;
  policies: PolicyBundle;
  policies_hash: string;
  updated_at: string | null;
}
export interface CompatibilityAnalysis {
  id: string;
  project_id: string;
  replay_session_id: string;
  comparison_id: string;
  request_method: string;
  endpoint_path: string;
  verdict: string;
  counts: Record<string, number>;
  effective_policy: EndpointPolicy | null;
  policy_hash: string;
  effective_comparison_rules: ComparisonRules;
  comparison_algorithm_version: string;
  engine_version: string;
  analyzed_at: string;
  is_current: boolean;
}
export interface CompatibilityRun {
  id: string;
  project_id: string;
  replay_session_id: string;
  engine_version: string;
  verdict: string;
  summary: Record<string, number>;
  analyzed_at: string;
  is_current: boolean;
  missing_result_ids: string[];
  metadata_snapshot: {
    project_name: string;
    session_name: string;
    source_base_urls: string[];
    target_base_url: string;
    session_status: string;
  };
  analyses: CompatibilityAnalysis[];
}
export interface CompatibilityFinding {
  id: string;
  analysis_id: string;
  difference_id: string | null;
  comparison_id: string;
  request_method: string;
  endpoint_path: string;
  ordinal: number;
  scope: string;
  path: string;
  change_type: string;
  classification: Classification;
  severity: Severity | null;
  confidence: "high" | "medium" | "low";
  title: string;
  explanation: string;
  recommended_action: string;
  rule_id: string;
  evidence: {
    old_present?: boolean;
    new_present?: boolean;
    old_value?: Json;
    new_value?: Json;
    old_preview?: string;
    new_preview?: string;
    old_value_truncated?: boolean;
    new_value_truncated?: boolean;
    requirement?: Json;
    baseline_already_violated?: boolean;
  };
}
export interface FindingsPage {
  items: CompatibilityFinding[];
  total: number;
  limit: number;
  offset: number;
}
export interface CompatibilityHistory {
  items: CompatibilityRun[];
  total: number;
  limit: number;
  offset: number;
}
export const classLabels: Record<Classification, string> = {
  confirmed_breaking: "Confirmed breaking",
  potentially_breaking: "Potentially breaking",
  informational: "Informational",
  unassessed: "Unassessed",
};
export const verdictLabels: Record<string, string> = {
  compatible_under_configured_policy: "Compatible under configured policy",
  potential_compatibility_issues: "Potential compatibility issues",
  incompatible_with_configured_contract:
    "Incompatible with configured contract",
  insufficient_evidence: "Insufficient evidence",
};
