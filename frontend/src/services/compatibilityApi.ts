import { request } from "./api";
import type {
  CompatibilityHistory,
  CompatibilityRun,
  FindingsPage,
  PolicyBundle,
  PolicySettings,
} from "../types/compatibility";
export const compatibilityApi = {
  assess: (id: string) =>
    request<CompatibilityRun>(`/replay-sessions/${id}/assess`, {
      method: "POST",
      body: "{}",
    }),
  policies: (id: string) =>
    request<PolicySettings>(`/projects/${id}/compatibility-policies`),
  savePolicies: (id: string, policies: PolicyBundle) =>
    request<PolicySettings>(`/projects/${id}/compatibility-policies`, {
      method: "PUT",
      body: JSON.stringify(policies),
    }),
  analyze: (id: string) =>
    request<CompatibilityRun>(`/replay-sessions/${id}/analyze`, {
      method: "POST",
      body: "{}",
    }),
  run: (id: string) => request<CompatibilityRun>(`/compatibility-runs/${id}`),
  history: (id: string, offset = 0) =>
    request<CompatibilityHistory>(
      `/projects/${id}/compatibility-runs?limit=20&offset=${offset}`,
    ),
  findings: (id: string, params: URLSearchParams) =>
    request<FindingsPage>(`/compatibility-runs/${id}/findings?${params}`),
};
