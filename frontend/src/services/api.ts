import type { Project, Recording, RecordingPage, SendPayload } from "../types";
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
  } catch {
    throw new Error(
      "Cannot reach API TimeMachine. Check that the backend is running.",
    );
  }
  const text = await response.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(
      "The backend returned an unreadable response. Check the backend and proxy configuration.",
    );
  }
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map(
                (e: { loc: string[]; msg: string }) =>
                  `${e.loc.slice(1).join(".")}: ${e.msg}`,
              )
              .join("; ")
          : `Request failed (${response.status}).`,
    );
  }
  return data as T;
}
export interface RuntimeConfig {
  sample_v1_base_url: string | null;
  sample_v2_base_url: string | null;
  max_executions_per_minute: number;
  deployment_mode: string;
  version: string;
}
export const api = {
  config: () => request<RuntimeConfig>("/config"),
  projects: () => request<Project[]>("/projects"),
  createProject: (data: {
    name: string;
    base_url: string;
    description?: string;
  }) =>
    request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateProject: (
    id: string,
    data: { name: string; base_url: string; description: string },
  ) =>
    request<Project>(`/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  send: (id: string, data: SendPayload) =>
    request<Recording>(`/projects/${id}/requests/send`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  recordings: (
    id: string,
    offset = 0,
    baseline = false,
    limit = 50,
    search = "",
    method = "",
  ) =>
    request<RecordingPage>(
      `/projects/${id}/recordings?offset=${offset}&limit=${limit}${baseline ? "&baseline=true" : ""}${search ? "&search=" + encodeURIComponent(search) : ""}${method ? "&method=" + encodeURIComponent(method) : ""}`,
    ),
  recording: (id: string) => request<Recording>(`/recordings/${id}`),
  updateRecording: (
    id: string,
    data: {
      name?: string;
      is_baseline?: boolean;
      environment_label?: string | null;
    },
  ) =>
    request<Recording>(`/recordings/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  health: () => request<{ status: string }>("/health"),
};
export const errorMessage = (e: unknown) =>
  e instanceof Error ? e.message : "Something went wrong. Try again.";
