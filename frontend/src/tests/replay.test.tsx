import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import {
  render,
  screen,
  within,
  waitFor,
  cleanup,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import type { Project, Recording } from "../types";
import type {
  ReplayPayload,
  ReplaySessionDetail,
  ReplayResult,
} from "../types/replay";
const date = "2026-11-17T10:00:00Z";
const project: Project = {
  id: "project-1",
  name: "Commerce API",
  description: null,
  base_url: "http://sample-api:8001",
  created_at: date,
  updated_at: date,
};
let recordings: Recording[],
  sessions: ReplaySessionDetail[],
  results: ReplayResult[],
  sent: ReplayPayload[],
  failTransport: boolean,
  createError: boolean,
  release: (() => void) | null,
  delayCreate: boolean;
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status });
const mount = (route = "/replay") =>
  render(
    <MemoryRouter initialEntries={[route]}>
      <App />
    </MemoryRouter>,
  );
function recording(id: string, name: string, method = "GET"): Recording {
  return {
    id,
    project_id: project.id,
    name,
    method,
    endpoint_path: method === "GET" ? "/users/1" : "/echo",
    response_status: 200,
    duration_ms: 8,
    captured_at: date,
    environment_label: "v1",
    is_baseline: true,
    execution_error: null,
    base_url: project.base_url,
    query_parameters: {},
    request_headers: {},
    request_body: method === "GET" ? null : { message: "hello" },
    request_body_present: method !== "GET",
    response_headers: { "content-type": "application/json" },
    response_body: { id: 1, name: "Maya Chen" },
    response_body_kind: "json",
    content_type: "application/json",
  };
}
beforeEach(() => {
  localStorage.clear();
  recordings = [
    recording("r1", "User v1"),
    recording("r2", "Echo v1", "POST"),
    recording("r3", "Private v1"),
  ];
  recordings[2].request_headers = { authorization: "[REDACTED]" };
  sessions = [];
  results = [];
  sent = [];
  failTransport = false;
  createError = false;
  release = null;
  delayCreate = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: RequestInit = {}) => {
      const path = url.replace("/api", "").split("?")[0],
        method = options.method || "GET";
      if (path === "/config")
        return json({
          sample_v1_base_url: "http://sample-api:8001",
          sample_v2_base_url: "http://sample-api-v2:8001",
          max_executions_per_minute: 120,
          deployment_mode: "trusted_local_single_user",
          version: "1.0.0",
        });
      if (path === "/health") return json({ status: "ok" });
      if (path === "/projects") return json([project]);
      if (path === "/replay-config")
        return json({
          allowed_target_origins: [
            "http://sample-api:8001",
            "http://sample-api-v2:8001",
          ],
          max_batch_size: 10,
          session_timeout_seconds: 120,
          execution_mode: "synchronous_sequential",
        });
      if (path === `/projects/${project.id}/recordings`)
        return json({
          items: recordings,
          total: recordings.length,
          limit: 20,
          offset: 0,
        });
      if (path.startsWith("/recordings/"))
        return json(recordings.find((r) => r.id === path.split("/")[2]));
      if (
        path === `/projects/${project.id}/replay-sessions` &&
        method === "GET"
      )
        return json({
          items: sessions,
          total: sessions.length,
          limit: 20,
          offset: 0,
        });
      if (
        path === `/projects/${project.id}/replay-sessions` &&
        method === "POST"
      ) {
        const payload = JSON.parse(String(options.body)) as ReplayPayload;
        sent.push(payload);
        if (delayCreate)
          await new Promise<void>((resolve) => {
            release = resolve;
          });
        if (createError)
          return json(
            { detail: "Database unavailable. Check history before retrying." },
            503,
          );
        const sessionId = "s" + (sessions.length + 1);
        const batch: ReplayResult[] = payload.recording_ids.map((id, i) => {
          const original = recordings.find((r) => r.id === id)!;
          return {
            id: sessionId + "-" + id,
            replay_session_id: sessionId,
            original_recording_id: id,
            ordinal: i,
            request_method: original.method,
            endpoint_path: original.endpoint_path,
            replay_url: payload.target_base_url + original.endpoint_path,
            outcome: failTransport ? "transport_error" : "http_response",
            response_status: failTransport
              ? null
              : original.method === "GET"
                ? 200
                : 201,
            duration_ms: 14,
            execution_error: failTransport
              ? {
                  code: "connection_error",
                  message: "Target could not be reached.",
                }
              : null,
            executed_at: date,
            request_metadata: {
              headers: {},
              query_parameters: {},
              body: original.request_body,
              body_present: original.request_body_present || false,
            },
            response_headers: { "content-type": "application/json" },
            response_body: failTransport
              ? null
              : { id: "1", full_name: "Maya Chen", account_status: "active" },
            response_body_kind: failTransport ? "omitted" : "json",
            content_type: "application/json",
            original_recording: original,
          };
        });
        results.push(...batch);
        const session: ReplaySessionDetail = {
          id: sessionId,
          project_id: project.id,
          name: payload.name,
          target_base_url: payload.target_base_url,
          status: failTransport ? "completed_with_errors" : "completed",
          total_requests: batch.length,
          completed_requests: batch.length,
          http_responses: failTransport ? 0 : batch.length,
          failed_requests: failTransport ? batch.length : 0,
          error_requests: failTransport ? batch.length : 0,
          skipped_requests: 0,
          started_at: date,
          completed_at: date,
          duration_ms: 20,
          results: batch,
        };
        sessions.unshift(session);
        return json(session, 201);
      }
      if (path.startsWith("/replay-sessions/"))
        return json(sessions.find((s) => s.id === path.split("/")[2]));
      if (path.startsWith("/replay-results/"))
        return json(results.find((r) => r.id === path.split("/")[2]));
      throw new Error(`Unexpected ${method} ${path}`);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("Replay workspace and history", () => {
  it("selects a recording, shows execution feedback, displays both responses, and reopens persisted history", async () => {
    delayCreate = true;
    mount();
    const user = userEvent.setup();
    await screen.findByLabelText("Select User v1");
    expect(sent).toHaveLength(0);
    expect(
      (screen.getByRole("button", { name: "Run replay" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    await user.click(screen.getByLabelText("Select User v1"));
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "Run replay",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );
    expect(
      (screen.getByLabelText("Replay target base URL") as HTMLInputElement)
        .value,
    ).toBe("http://sample-api-v2:8001");
    await user.click(screen.getByRole("button", { name: "Run replay" }));
    await screen.findByText("Executing 1 request sequentially");
    expect(sent[0].recording_ids).toEqual(["r1"]);
    expect(sent[0].confirm_side_effects).toBe(false);
    release!();
    await screen.findByRole("heading", { name: "Replay results" });
    const original = await screen.findByRole("article", {
        name: "Original recording",
      }),
      replayed = screen.getByRole("article", { name: "Replayed response" });
    expect(original.textContent).toContain('"name":');
    expect(replayed.textContent).toContain('"full_name":');
    expect(original.textContent).toContain("http://sample-api:8001/users/1");
    expect(replayed.textContent).toContain("http://sample-api-v2:8001/users/1");
    cleanup();
    mount("/replay/history");
    await user.click(
      await screen.findByRole("link", { name: /API v2 regression run/ }),
    );
    await screen.findByRole("article", { name: "Replayed response" });
    expect(sent).toHaveLength(1);
  });

  it("requires explicit confirmation for a batch containing POST and lets the user inspect each result", async () => {
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText("Select User v1"));
    await waitFor(() =>
      expect(
        (screen.getByLabelText("Select Echo v1") as HTMLInputElement).disabled,
      ).toBe(false),
    );
    await user.click(screen.getByLabelText("Select Echo v1"));
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "Run replay",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );
    await user.click(screen.getByRole("button", { name: "Run replay" }));
    let dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("can change data");
    expect(sent).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(sent).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Run replay" }));
    dialog = screen.getByRole("dialog");
    await user.click(
      within(dialog).getByRole("button", { name: "Confirm and run" }),
    );
    await screen.findByRole("heading", { name: "Replay results" });
    expect(sent[0].recording_ids).toEqual(["r1", "r2"]);
    expect(sent[0].confirm_side_effects).toBe(true);
    await user.click(
      await screen.findByRole("button", { name: "Inspect POST /echo" }),
    );
    await screen.findByRole("article", { name: "Replayed response" });
    await waitFor(() =>
      expect(
        screen.getByRole("article", { name: "Replayed response" }).textContent,
      ).toContain("201"),
    );
    expect(
      screen.getByRole("region", { name: "Replay summary" }).textContent,
    ).toContain("2 / 2");
  });

  it("validates targets and masked credentials, and clears temporary values after a failed submission", async () => {
    createError = true;
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText("Select Private v1"));
    await screen.findByText(/Masked values remain/);
    expect(
      (screen.getByRole("button", { name: "Run replay" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    await user.click(screen.getByText("Temporary headers"));
    await user.click(
      screen.getByRole("button", { name: "Add temporary header" }),
    );
    await user.type(
      screen.getByLabelText("Temporary header name 1"),
      "Authorization",
    );
    await user.type(
      screen.getByLabelText("Temporary header value 1"),
      "Bearer session-only-secret",
    );
    const target = screen.getByLabelText("Replay target base URL");
    await user.clear(target);
    await user.type(target, "https://unapproved.test");
    await screen.findByText(/Choose an approved target/);
    expect(
      (screen.getByRole("button", { name: "Run replay" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    await user.clear(target);
    await user.type(target, "http://sample-api-v2:8001");
    await user.click(screen.getByRole("button", { name: "Run replay" }));
    await screen.findByRole("alert");
    expect(sent[0].temporary_headers.Authorization).toBe(
      "Bearer session-only-secret",
    );
    expect(screen.queryByLabelText("Temporary header value 1")).toBeNull();
    expect(JSON.stringify(localStorage)).not.toContain("session-only-secret");
    expect(screen.getByRole("alert").textContent).toContain(
      "history before repeating",
    );
  });

  it("shows a failed replay without inventing an HTTP response or hiding the original", async () => {
    failTransport = true;
    mount();
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText("Select User v1"));
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "Run replay",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );
    await user.click(screen.getByRole("button", { name: "Run replay" }));
    const replayed = await screen.findByRole("article", {
      name: "Replayed response",
    });
    expect(replayed.textContent).toContain("No HTTP response");
    expect(replayed.textContent).toContain("Target could not be reached.");
    expect(
      screen.getByRole("article", { name: "Original recording" }).textContent,
    ).toContain("200");
    expect(replayed.textContent).not.toContain("200");
  });

  it("requires a choice for legacy body presence and sends the supported override", async () => {
    recordings[0].request_body_present = null;
    mount("/replay?recording=r1");
    const user = userEvent.setup();
    await screen.findByText(/A legacy recording has unknown body presence/);
    expect(
      (screen.getByRole("button", { name: "Run replay" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    await user.click(screen.getByText("Inspect / override"));
    await user.selectOptions(screen.getByLabelText("Body mode for r1"), "omit");
    await user.click(screen.getByRole("button", { name: "Run replay" }));
    await screen.findByRole("heading", { name: "Replay results" });
    expect(sent[0].overrides.r1).toEqual({ omit_body: true });
  });
});
