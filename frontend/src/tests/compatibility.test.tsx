import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Compatibility } from "../pages/Compatibility";
import type {
  CompatibilityFinding,
  CompatibilityRun,
  PolicySettings,
} from "../types/compatibility";
const date = "2026-11-18T10:00:00Z";
const project = {
  id: "p1",
  name: "Commerce",
  description: null,
  base_url: "http://sample-api:8001",
  created_at: date,
  updated_at: date,
};
const policy = {
  method: "GET" as const,
  endpoint_path: "/users/1",
  expected_status_codes: [200],
  required_json_paths: ["/id"],
  expected_types: {},
  required_headers: [],
  allowed_content_types: [],
  allow_additional_fields: null,
  dynamic_json_paths: [],
};
let policies: PolicySettings,
  runs: CompatibilityRun[],
  requests: string[],
  posts: number,
  fail: boolean,
  rejectPolicy: boolean;
function savedRun(id = "run1"): CompatibilityRun {
  return {
    id,
    project_id: "p1",
    replay_session_id: "s1",
    engine_version: "compatibility-v1",
    verdict: "incompatible_with_configured_contract",
    analyzed_at: date,
    is_current: true,
    missing_result_ids: [],
    summary: {
      replayed: 1,
      compared: 1,
      identical: 0,
      changed: 1,
      confirmed_breaking: 1,
      potentially_breaking: 0,
      informational: 0,
      unassessed: 0,
      high_critical: 1,
      transport_failures: 0,
      missing_comparisons: 0,
      incomplete_comparisons: 0,
    },
    metadata_snapshot: {
      project_name: "Commerce",
      session_name: "Release candidate",
      source_base_urls: ["http://sample-api:8001"],
      target_base_url: "http://sample-api-v2:8001",
      session_status: "completed",
    },
    analyses: [
      {
        id: "a1",
        project_id: "p1",
        replay_session_id: "s1",
        comparison_id: "c1",
        request_method: "GET",
        endpoint_path: "/users/1",
        verdict: "incompatible_with_configured_contract",
        counts: { confirmed_breaking: 1, findings: 1 },
        effective_policy: policy,
        policy_hash: "hash",
        effective_comparison_rules: {
          ignored_headers: [],
          ignored_json_paths: [],
          unordered_array_paths: [],
        },
        comparison_algorithm_version: "pointer-v1",
        engine_version: "compatibility-v1",
        analyzed_at: date,
        is_current: true,
      },
    ],
  };
}
const finding: CompatibilityFinding = {
  id: "f1",
  analysis_id: "a1",
  difference_id: "d1",
  comparison_id: "c1",
  request_method: "GET",
  endpoint_path: "/users/1",
  ordinal: 0,
  scope: "body",
  path: "/id",
  change_type: "field_removed",
  classification: "confirmed_breaking",
  severity: "high",
  confidence: "high",
  title: "Required JSON path is absent",
  explanation: "The declared required field was removed.",
  recommended_action: "Restore the required id.",
  rule_id: "contract.required_path",
  evidence: {
    old_present: true,
    new_present: false,
    old_preview: "1",
    new_preview: "Missing",
    requirement: "/id",
  },
};
function reply(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
beforeEach(() => {
  policies = {
    project_id: "p1",
    policies: { endpoints: [] },
    policies_hash: "none",
    updated_at: null,
  };
  runs = [savedRun()];
  requests = [];
  posts = 0;
  fail = false;
  rejectPolicy = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      requests.push(input);
      const url = new URL(input, "http://localhost");
      if (fail)
        return reply({ detail: "Database temporarily unavailable" }, 503);
      if (input.startsWith("/api/projects/p1/replay-sessions"))
        return reply({
          items: [
            {
              id: "s1",
              name: "Release candidate",
              status: "completed",
              total_requests: 1,
            },
          ],
          total: 1,
          offset: 0,
          limit: 20,
        });
      if (input === "/api/projects/p1/compatibility-policies") {
        if (init?.method === "PUT") {
          if (rejectPolicy)
            return reply(
              { detail: "Expected status codes must be from 200 to 299." },
              422,
            );
          policies = {
            ...policies,
            policies: JSON.parse(String(init.body)),
            policies_hash: "saved",
          };
          runs = runs.map((r) => ({ ...r, is_current: false }));
        }
        return reply(policies);
      }
      if (input.startsWith("/api/projects/p1/compatibility-runs"))
        return reply({ items: runs, total: runs.length, limit: 20, offset: 0 });
      if (
        input === "/api/replay-sessions/s1/analyze" ||
        input === "/api/replay-sessions/s1/assess"
      ) {
        posts++;
        const r = savedRun("run" + (runs.length + 1));
        runs = [r, ...runs];
        return reply(r);
      }
      if (url.pathname.endsWith("/findings")) {
        const empty =
          url.searchParams.get("classification") === "informational" ||
          url.searchParams.get("method") === "POST" ||
          url.searchParams.get("search") === "none";
        return reply({
          items: empty ? [] : [finding],
          total: empty ? 0 : 1,
          limit: 25,
          offset: 0,
        });
      }
      if (input.startsWith("/api/compatibility-runs/"))
        return reply(runs.find((r) => input.endsWith("/" + r.id)));
      return reply({ detail: "Unexpected request " + input }, 404);
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function mount(path = "/compatibility?session=s1&run=run1") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Compatibility project={project} />
    </MemoryRouter>,
  );
}
describe("compatibility workspace", () => {
  it("shows scoped verdict, evidence, exact difference link, frozen policy and download links", async () => {
    mount();
    expect(
      await screen.findByRole("heading", {
        name: "Incompatible with configured contract",
      }),
    ).toBeTruthy();
    expect(
      screen.getByText(/not a universal compatibility guarantee/),
    ).toBeTruthy();
    await userEvent.click(
      await screen.findByText("Required JSON path is absent"),
    );
    expect(screen.getByText("Restore the required id.")).toBeTruthy();
    expect(screen.getByText("Missing")).toBeTruthy();
    expect(
      screen
        .getByRole("link", { name: "Open saved Phase 3 difference" })
        .getAttribute("href"),
    ).toBe("/comparisons/c1?difference=d1");
    expect(
      screen.getByRole("link", { name: "Download JSON" }).getAttribute("href"),
    ).toBe("/api/compatibility-runs/run1/report?format=json");
    expect(
      screen
        .getByRole("link", { name: "Download HTML" })
        .hasAttribute("download"),
    ).toBe(true);
    await userEvent.click(
      screen.getByText("Frozen policies and source comparisons"),
    );
    expect(screen.getByText("GET /users/1 · Current settings")).toBeTruthy();
  });
  it("filters by classification, severity, method, endpoint and search", async () => {
    mount();
    await screen.findByText("Required JSON path is absent");
    await userEvent.selectOptions(
      screen.getByLabelText("Classification"),
      "informational",
    );
    expect(await screen.findByText("No matching findings")).toBeTruthy();
    await userEvent.selectOptions(
      screen.getByLabelText("Classification"),
      "confirmed_breaking",
    );
    await userEvent.selectOptions(screen.getByLabelText("Severity"), "high");
    await userEvent.selectOptions(screen.getByLabelText("Method"), "GET");
    fireEvent.change(screen.getByLabelText("Endpoint contains"), {
      target: { value: "/users" },
    });
    fireEvent.change(screen.getByLabelText("Search path or title"), {
      target: { value: "required" },
    });
    await waitFor(() =>
      expect(
        requests.some(
          (p) =>
            p.includes("classification=confirmed_breaking") &&
            p.includes("severity=high") &&
            p.includes("method=GET") &&
            p.includes("endpoint=%2Fusers") &&
            p.includes("search=required"),
        ),
      ).toBe(true),
    );
  });
  it("validates policy input, preserves history, and requires explicit reanalysis", async () => {
    mount();
    await screen.findByRole("heading", {
      name: "Incompatible with configured contract",
    });
    await userEvent.click(screen.getByText("Endpoint compatibility policies"));
    const editor = screen.getByLabelText("Policies JSON");
    fireEvent.change(editor, { target: { value: "{bad" } });
    await userEvent.click(
      screen.getByRole("button", { name: "Save policies" }),
    );
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Invalid policy JSON",
    );
    fireEvent.change(editor, {
      target: { value: JSON.stringify({ endpoints: [policy] }) },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Save policies" }),
    );
    expect(
      await screen.findByText(/Policies saved. Select Analyze session/),
    ).toBeTruthy();
    expect(posts).toBe(0);
    expect(
      await screen.findByText(/older policies\/comparison rules/),
    ).toBeTruthy();
    await userEvent.click(
      screen.getByRole("button", { name: "Analyze session" }),
    );
    await waitFor(() => expect(posts).toBe(1));
    expect(await screen.findByText("2 saved analyses")).toBeTruthy();
    await waitFor(() =>
      expect(
        screen
          .getByRole("link", { name: "Download JSON" })
          .getAttribute("href"),
      ).toBe("/api/compatibility-runs/run2/report?format=json"),
    );
  });
  it("shows server policy validation without discarding the draft", async () => {
    rejectPolicy = true;
    mount("/compatibility");
    await userEvent.click(
      await screen.findByText("Endpoint compatibility policies"),
    );
    const draft = JSON.stringify({
      endpoints: [{ ...policy, expected_status_codes: [500] }],
    });
    fireEvent.change(screen.getByLabelText("Policies JSON"), {
      target: { value: draft },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "Save policies" }),
    );
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Expected status codes",
    );
    expect(
      (screen.getByLabelText("Policies JSON") as HTMLTextAreaElement).value,
    ).toBe(draft);
  });
  it("shows empty states, historical links and recoverable errors", async () => {
    runs = [];
    mount("/compatibility");
    expect(
      await screen.findByText("No compatibility analyses yet"),
    ).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: "Analyze session",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    cleanup();
    fail = true;
    mount("/compatibility");
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Database temporarily unavailable",
    );
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(
      await screen.findByText("No compatibility analyses yet"),
    ).toBeTruthy();
  });
});

it("compares and analyzes saved evidence in one explicit action", async () => {
  mount("/compatibility?session=s1");
  await userEvent.click(
    await screen.findByRole("button", { name: "Compare & analyze" }),
  );
  await waitFor(() =>
    expect(requests).toContain("/api/replay-sessions/s1/assess"),
  );
  expect(
    await screen.findByRole("heading", {
      name: "Incompatible with configured contract",
    }),
  ).toBeTruthy();
});
it("reuses historical reports without presenting a second execution workspace", async () => {
  render(
    <MemoryRouter initialEntries={["/reports?run=run1"]}>
      <Compatibility project={project} reportsOnly />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("heading", { name: "Reports" })).toBeTruthy();
  expect(screen.queryByLabelText("Session to analyze")).toBeNull();
  expect(
    await screen.findByRole("link", { name: "Download JSON" }),
  ).toBeTruthy();
  expect(screen.queryByText("Endpoint compatibility policies")).toBeNull();
  expect(posts).toBe(0);
});
