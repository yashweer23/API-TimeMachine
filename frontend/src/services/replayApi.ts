import { request } from "./api";
import type {
  ReplayConfig,
  ReplayPayload,
  ReplayResult,
  ReplaySessionDetail,
  ReplaySessionPage,
} from "../types/replay";
export const replayApi = {
  config: () => request<ReplayConfig>("/replay-config"),
  create: (projectId: string, data: ReplayPayload) =>
    request<ReplaySessionDetail>(`/projects/${projectId}/replay-sessions`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  sessions: (projectId: string, offset = 0) =>
    request<ReplaySessionPage>(
      `/projects/${projectId}/replay-sessions?limit=20&offset=${offset}`,
    ),
  session: (id: string) =>
    request<ReplaySessionDetail>(`/replay-sessions/${id}`),
  result: (id: string) => request<ReplayResult>(`/replay-results/${id}`),
};
