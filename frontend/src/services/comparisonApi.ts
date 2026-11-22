import { request } from "./api";
import type {
  ComparisonDetail,
  ComparisonPage,
  ComparisonRules,
  DifferenceValues,
  RulesSettings,
  SessionComparisons,
} from "../types/comparison";
export const comparisonApi = {
  settings: (id: string) =>
    request<RulesSettings>(`/projects/${id}/comparison-settings`),
  saveSettings: (id: string, rules: ComparisonRules) =>
    request<RulesSettings>(`/projects/${id}/comparison-settings`, {
      method: "PUT",
      body: JSON.stringify(rules),
    }),
  compare: (id: string, rules?: ComparisonRules) =>
    request<ComparisonDetail>(`/replay-results/${id}/compare`, {
      method: "POST",
      body: JSON.stringify(rules ? { rules } : {}),
    }),
  detail: (id: string) => request<ComparisonDetail>(`/comparisons/${id}`),
  latest: (id: string) =>
    request<ComparisonDetail>(`/replay-results/${id}/comparison`),
  session: (id: string) =>
    request<SessionComparisons>(`/replay-sessions/${id}/comparisons`),
  compareSession: (id: string) =>
    request<SessionComparisons>(`/replay-sessions/${id}/compare`, {
      method: "POST",
      body: "{}",
    }),
  history: (id: string, offset = 0) =>
    request<ComparisonPage>(
      `/projects/${id}/comparisons?offset=${offset}&limit=20`,
    ),
  values: (comparison: string, difference: string) =>
    request<DifferenceValues>(
      `/comparisons/${comparison}/differences/${difference}/values`,
    ),
};
