import type { Json } from "./index";
export interface ComparisonRules {
  ignored_json_paths: string[];
  ignored_headers: string[];
  unordered_array_paths: string[];
}
export interface RulesSettings {
  project_id: string;
  rules: ComparisonRules;
  rules_hash: string;
  updated_at: string | null;
}
export type ChangeType =
  | "field_added"
  | "field_removed"
  | "value_changed"
  | "type_changed"
  | "array_changed"
  | "status_changed"
  | "header_added"
  | "header_removed"
  | "header_changed"
  | "text_changed";
export interface Difference {
  id: string;
  ordinal: number;
  scope: "body" | "headers" | "status";
  path: string;
  change_type: ChangeType;
  old_type: string;
  new_type: string;
  old_present: boolean;
  new_present: boolean;
  old_value: Json;
  new_value: Json;
  old_preview: string;
  new_preview: string;
  old_value_truncated: boolean;
  new_value_truncated: boolean;
}
export interface ComparisonSummary {
  id: string;
  replay_result_id: string;
  comparison_status:
    | "identical"
    | "different"
    | "partial"
    | "unavailable"
    | "limited";
  original_status_code: number | null;
  replay_status_code: number | null;
  total_differences: number;
  counts: Record<ChangeType, number>;
  effective_rules: ComparisonRules;
  rules_hash: string;
  algorithm_version: string;
  compared_at: string;
  notes: string[];
  is_current: boolean;
  project_id: string;
  replay_session_id: string;
  session_name: string;
  recording_name: string;
  request_method: string;
  endpoint_path: string;
}
export interface ComparisonDetail extends ComparisonSummary {
  differences: Difference[];
}
export interface ComparisonPage {
  items: ComparisonSummary[];
  total: number;
  limit: number;
  offset: number;
}
export interface SessionComparisons {
  session_id: string;
  project_id: string;
  session_name: string;
  total_requests: number;
  pending_requests: number;
  items: ComparisonSummary[];
  totals: Record<string, number>;
}
export interface DifferenceValues {
  old_present: boolean;
  new_present: boolean;
  old_value: Json;
  new_value: Json;
}
export const changeLabels: Record<ChangeType, string> = {
  field_added: "Added",
  field_removed: "Removed",
  value_changed: "Value changed",
  type_changed: "Type changed",
  array_changed: "Array changed",
  status_changed: "Status changed",
  header_added: "Header added",
  header_removed: "Header removed",
  header_changed: "Header changed",
  text_changed: "Text changed",
};
export const pointerChild = (path: string, key: string | number) =>
  path + "/" + String(key).replaceAll("~", "~0").replaceAll("/", "~1");
