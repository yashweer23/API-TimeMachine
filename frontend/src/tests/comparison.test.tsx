import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import type { Project } from "../types";
import type {
  ComparisonDetail,
  ComparisonRules,
  Difference,
} from "../types/comparison";
import type { ReplayResult, ReplaySession } from "../types/replay";
const date = "2026-11-18T00:00:00Z";
const project: Project = {
  id: "p1",
  name: "Comparison project",
  description: null,
  base_url: "http://sample-api:8001",
  created_at: date,
  updated_at: date,
};
const counts = {
  field_added: 1,
  field_removed: 1,
  type_changed: 1,
  value_changed: 0,
  array_changed: 0,
  status_changed: 0,
  header_added: 0,
  header_removed: 0,
  header_changed: 0,
  text_changed: 0,
};
const differences: Difference[] = [
  {
    id: "d1",
    ordinal: 0,
    scope: "body",
    path: "/age",
    change_type: "type_changed",
    old_type: "number",
    new_type: "string",
    old_present: true,
    new_present: true,
    old_value: 24,
    new_value: "24",
    old_preview: "24",
    new_preview: '"24"',
    old_value_truncated: false,
    new_value_truncated: false,
  },
  {
    id: "d2",
    ordinal: 1,
    scope: "body",
    path: "/full_name",
    change_type: "field_added",
    old_type: "missing",
    new_type: "string",
    old_present: false,
    new_present: true,
    old_value: null,
    new_value: "Alex",
    old_preview: "Missing",
    new_preview: '"Alex"',
    old_value_truncated: false,
    new_value_truncated: false,
  },
  {
    id: "d3",
    ordinal: 2,
    scope: "body",
    path: "/name",
    change_type: "field_removed",
    old_type: "string",
    new_type: "missing",
    old_present: true,
    new_present: false,
    old_value: "Alex",
    new_value: null,
    old_preview: '"Alex"',
    new_preview: "Missing",
    old_value_truncated: false,
    new_value_truncated: false,
  },
];
let rules: ComparisonRules,
  saved: boolean,
  empty: boolean,
  unavailable: boolean,
  fail: boolean,
  posts: number,
  puts: number;
function comparison(id = "c1"): ComparisonDetail {
  return {
    id,
    replay_result_id: "r1",
    comparison_status: unavailable
      ? "unavailable"
      : id === "c2"
        ? "identical"
        : "different",
    original_status_code: 200,
    replay_status_code: unavailable ? null : 200,
    total_differences: id === "c2" || unavailable ? 0 : 3,
    counts:
      id === "c2" || unavailable
        ? (Object.fromEntries(
            Object.keys(counts).map((k) => [k, 0]),
          ) as typeof counts)
        : counts,
    effective_rules:
      id === "c2"
        ? rules
        : {
            ignored_json_paths: [],
            ignored_headers: ["date"],
            unordered_array_paths: [],
          },
    rules_hash: id === "c2" ? "updated" : "initial",
    algorithm_version: "pointer-v1",
    compared_at: date,
    notes: unavailable ? ["A complete HTTP response is unavailable."] : [],
    is_current: id === "c2" || !saved,
    project_id: "p1",
    replay_session_id: "s1",
    session_name: "Regression run",
    recording_name: "User v1",
    request_method: "GET",
    endpoint_path: "/users/1",
    differences: id === "c2" || unavailable ? [] : differences,
  };
}
const session: ReplaySession = {
  id: "s1",
  project_id: "p1",
  name: "Regression run",
  target_base_url: "http://sample-api-v2:8001",
  status: "completed",
  total_requests: 1,
  completed_requests: 1,
  failed_requests: 0,
  error_requests: 0,
  http_responses: 1,
  skipped_requests: 0,
  started_at: date,
  completed_at: date,
  duration_ms: 20,
};
const result: ReplayResult = {
  id: "r1",
  replay_session_id: "s1",
  original_recording_id: "o1",
  ordinal: 0,
  request_method: "GET",
  endpoint_path: "/users/1",
  replay_url: "http://sample-api-v2:8001/users/1",
  outcome: "http_response",
  response_status: 200,
  duration_ms: 10,
  execution_error: null,
  executed_at: date,
  request_metadata: {
    headers: {},
    query_parameters: {},
    body: null,
    body_present: false,
  },
  response_headers: { "content-type": "application/json" },
  response_body: { age: "24", full_name: "Alex" },
  response_body_kind: "json",
  content_type: "application/json",
  original_recording: {
    id: "o1",
    project_id: "p1",
    name: "User v1",
    method: "GET",
    endpoint_path: "/users/1",
    response_status: 200,
    duration_ms: 10,
    captured_at: date,
    environment_label: null,
    is_baseline: false,
    execution_error: null,
    base_url: "http://sample-api:8001",
    query_parameters: {},
    request_headers: {},
    request_body: null,
    request_body_present: false,
    response_headers: { "content-type": "application/json" },
    response_body: { age: 24, name: "Alex" },
    response_body_kind: "json",
    content_type: "application/json",
  },
};
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status });
const mount = (path = "/comparisons?session=s1") =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
beforeEach(() => {
  localStorage.clear();
  rules = {
    ignored_json_paths: [],
    ignored_headers: ["date"],
    unordered_array_paths: [],
  };
  saved = false;
  empty = false;
  unavailable = false;
  fail = false;
  posts = 0;
  puts = 0;
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
      if (path === "/projects/p1/replay-sessions")
        return json({
          items: empty ? [] : [session],
          total: empty ? 0 : 1,
          limit: 20,
          offset: 0,
        });
      if (path === "/projects/p1/comparison-settings") {
        if (method === "PUT") {
          rules = JSON.parse(String(options.body));
          saved = true;
          puts++;
        }
        return json({
          project_id: "p1",
          rules,
          rules_hash: saved ? "updated" : "initial",
          updated_at: date,
        });
      }
      if (path === "/projects/p1/comparisons")
        return json({
          items: empty
            ? []
            : saved
              ? [comparison("c2"), comparison()]
              : [comparison()],
          total: empty ? 0 : saved ? 2 : 1,
          limit: 20,
          offset: 0,
        });
      if (
        path === "/replay-sessions/s1/comparisons" ||
        path === "/replay-sessions/s1/compare"
      ) {
        if (method === "POST") posts++;
        return json({
          session_id: "s1",
          project_id: "p1",
          session_name: "Regression run",
          total_requests: 1,
          pending_requests: 0,
          items: empty ? [] : [comparison(saved ? "c2" : "c1")],
          totals: {
            compared: empty ? 0 : 1,
            identical: 0,
            different: empty ? 0 : 1,
            incomparable: 0,
            differences: empty ? 0 : 3,
            ...counts,
          },
        });
      }
      if (path === "/replay-results/r1/compare") {
        posts++;
        return json(comparison(saved ? "c2" : "c1"));
      }
      if (path === "/replay-results/r1")
        return json(
          unavailable
            ? {
                ...result,
                response_status: null,
                response_body_kind: "omitted",
                response_body: null,
                execution_error: {
                  code: "timeout",
                  message: "Target timed out.",
                },
              }
            : result,
        );
      if (path.startsWith("/comparisons/"))
        return fail
          ? json({ detail: "Comparison service unavailable" }, 503)
          : json(comparison(path.split("/")[2]));
      throw new Error(`Unexpected ${method} ${path}`);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("Comparison workspace", () => {
  it("loads session counts and history, explicitly compares, then opens highlighted responses", async () => {
    mount();
    const user = userEvent.setup();
    await screen.findByText("3", { selector: ".comparison-stat strong" });
    expect(posts).toBe(0);
    await user.click(screen.getByRole("button", { name: "Compare session" }));
    await waitFor(() => expect(posts).toBe(1));
    await user.click(
      await screen.findByRole("link", { name: /GET.*users\/1.*User v1/ }),
    );
    await screen.findByRole("region", {
      name: "Highlighted response comparison",
    });
    expect(
      screen.getByRole("region", { name: "Comparison summary" }).textContent,
    ).toContain("3 detected differences");
    expect(
      screen.getByRole("article", { name: "Original highlighted response" })
        .textContent,
    ).toContain("Removed");
    expect(
      screen.getByRole("article", { name: "Replayed highlighted response" })
        .textContent,
    ).toContain("Added");
    cleanup();
    mount("/comparisons");
    await screen.findByRole("region", { name: "Comparison history" });
    expect(
      await screen.findByRole("link", { name: /User v1.*Regression run/ }),
    ).toBeTruthy();
    expect(posts).toBe(1);
  });
  it("filters and searches paths, expands exact values and navigates highlighted differences", async () => {
    mount("/comparisons/c1");
    const user = userEvent.setup();
    const explorer = await screen.findByRole("region", {
      name: "Difference explorer",
    });
    await user.selectOptions(
      within(explorer).getByLabelText("Filter changes"),
      "type_changed",
    );
    expect(
      within(explorer).queryByRole("button", { name: /Inspect body \/name/ }),
    ).toBeNull();
    await user.click(
      within(explorer).getByRole("button", {
        name: "Inspect body /age Type changed",
      }),
    );
    expect(within(explorer).getByText("Original · number")).toBeTruthy();
    expect(within(explorer).getByText("Replayed · string")).toBeTruthy();
    await user.selectOptions(
      within(explorer).getByLabelText("Filter changes"),
      "all",
    );
    await user.type(
      within(explorer).getByLabelText("Search difference paths"),
      "/full_name",
    );
    expect(
      within(explorer).getByRole("button", {
        name: "Inspect body /full_name Added",
      }),
    ).toBeTruthy();
    expect(
      within(explorer).queryByRole("button", { name: /Inspect body \/age/ }),
    ).toBeNull();
    await user.click(
      await screen.findByRole("button", { name: "Next difference" }),
    );
    expect(
      document.querySelector('.json-node[data-current="true"]')?.textContent,
    ).toContain("full_name");
  });
  it("validates ignore paths, saves rules, warns about historical settings and recalculates", async () => {
    mount("/comparisons/c1");
    const user = userEvent.setup();
    await user.click(await screen.findByText("Comparison rules"));
    const input = screen.getByLabelText("Ignored JSON paths");
    await user.type(input, "$.age");
    await user.click(
      screen.getByRole("button", { name: "Save comparison rules" }),
    );
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(puts).toBe(0);
    await user.clear(input);
    await user.type(input, "/age\n/name\n/full_name");
    await user.click(
      screen.getByRole("button", { name: "Save comparison rules" }),
    );
    await screen.findByText(/This historical comparison uses older settings/);
    expect(puts).toBe(1);
    expect(posts).toBe(0);
    await user.click(
      screen.getByRole("button", { name: "Recalculate with current rules" }),
    );
    await screen.findByText("0 detected differences");
    await screen.findByText("No differences under these rules");
    expect(posts).toBe(1);
  });
  it("shows unavailable execution data and useful error retry states", async () => {
    fail = true;
    mount("/comparisons/c1");
    const user = userEvent.setup();
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Comparison service unavailable",
    );
    unavailable = true;
    fail = false;
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByText("A complete HTTP response is unavailable.");
    const replayed = await screen.findByRole("article", {
      name: "Replayed highlighted response",
    });
    expect(replayed.textContent).toContain("No HTTP response");
    expect(replayed.textContent).toContain("Target timed out.");
  });
  it("shows empty history without creating comparisons automatically", async () => {
    empty = true;
    mount("/comparisons");
    await screen.findByText("No saved comparisons");
    expect(posts).toBe(0);
    expect(
      (
        screen.getByRole("button", {
          name: "Compare session",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
});
