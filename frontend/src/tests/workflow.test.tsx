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
import type { Project, Recording, SendPayload } from "../types";

let projects: Project[],
  recordings: Recording[],
  calls: { path: string; method: string; body: any }[];
const date = "2026-11-17T10:00:00Z";
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
function mount(route = "/") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <App />
    </MemoryRouter>,
  );
}
beforeEach(() => {
  localStorage.clear();
  projects = [];
  recordings = [];
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options: RequestInit = {}) => {
      const method = options.method || "GET",
        path = url.replace("/api", "").split("?")[0];
      const body = options.body ? JSON.parse(String(options.body)) : undefined;
      calls.push({ path, method, body });
      if (path === "/config")
        return json({
          sample_v1_base_url: "http://sample-api:8001",
          sample_v2_base_url: "http://sample-api-v2:8001",
          max_executions_per_minute: 120,
          deployment_mode: "trusted_local_single_user",
          version: "1.0.0",
        });
      if (path === "/health") return json({ status: "ok" });
      if (path === "/projects" && method === "GET") return json(projects);
      if (path === "/projects" && method === "POST") {
        const p: Project = {
          id: `project-${projects.length + 1}`,
          description: null,
          created_at: date,
          updated_at: date,
          ...body,
        };
        projects.unshift(p);
        return json(p, 201);
      }
      if (path.startsWith("/projects/") && path.endsWith("/recordings")) {
        const params = new URL(url, "http://localhost").searchParams;
        const items = recordings.filter(
          (r) =>
            r.project_id === path.split("/")[2] &&
            (!params.has("baseline") || r.is_baseline),
        );
        return json({ items, total: items.length, limit: 50, offset: 0 });
      }
      if (path.endsWith("/requests/send")) {
        const payload = body as SendPayload;
        const r: Recording = {
          id: `record-${recordings.length + 1}`,
          project_id: path.split("/")[2],
          name: body.name || `${body.method} ${body.endpoint_path}`,
          method: body.method,
          endpoint_path: body.endpoint_path,
          base_url: projects[0].base_url,
          query_parameters: body.query_parameters,
          request_headers: body.headers,
          request_body: body.body || null,
          request_body_present: Object.hasOwn(body, "body"),
          response_status: 200,
          response_headers: { "content-type": "application/json" },
          response_body:
            payload.method === "GET"
              ? { data: [{ id: 1, name: "Maya Chen" }] }
              : { received: payload.body ?? null },
          response_body_kind: "json",
          content_type: "application/json",
          duration_ms: 12.4,
          captured_at: date,
          environment_label: payload.environment_label || null,
          is_baseline: false,
          execution_error: null,
        };
        recordings.unshift(r);
        return json(r, 201);
      }
      if (path.startsWith("/recordings/")) {
        const r = recordings.find((r) => r.id === path.split("/")[2]);
        if (!r) return json({ detail: "Not found" }, 404);
        if (method === "PATCH") Object.assign(r, body);
        return json(r);
      }
      if (path.startsWith("/projects/") && method === "PATCH") {
        const p = projects.find((p) => p.id === path.split("/")[2]);
        Object.assign(p!, body, { updated_at: "2026-11-17T11:00:00Z" });
        return json(p);
      }
      throw new Error(`Unexpected request ${method} ${path}`);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

async function createProject() {
  const user = userEvent.setup();
  await screen.findByRole("button", { name: "Start with the sample API" });
  await user.click(screen.getByRole("button", { name: "New project" }));
  const dialog = screen.getByRole("dialog");
  await user.type(
    within(dialog).getByLabelText("Project name"),
    "Commerce API",
  );
  await user.click(
    within(dialog).getByRole("button", { name: "Create project" }),
  );
  await screen.findByRole("heading", { name: "Request workspace" });
  return user;
}

describe("Phase 1 workspace", () => {
  it("creates a project, sends GET, renames and marks a baseline, and reloads the saved capture", async () => {
    mount();
    const user = await createProject();
    await user.click(screen.getByRole("button", { name: "Send request" }));
    await screen.findByText('"Maya Chen"');
    const response = screen.getByRole("region", { name: "Response" });
    await user.click(
      within(response).getByRole("button", { name: "Mark baseline" }),
    );
    await waitFor(() => expect(recordings[0].is_baseline).toBe(true));
    await user.click(
      within(response).getByRole("button", { name: "GET /users" }),
    );
    const input = within(response).getByLabelText("Recording name");
    await user.clear(input);
    await user.type(input, "Users reference v1");
    await user.click(
      within(response).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() => expect(recordings[0].name).toBe("Users reference v1"));
    expect(localStorage.getItem("atm-project")).toBe("project-1");
    cleanup();
    mount("/recordings");
    await screen.findByText("Users reference v1");
    await user.click(screen.getByRole("button", { name: "Baselines" }));
    await user.click(
      await screen.findByRole("link", {
        name: /GET.*Users reference v1.*\/users/,
      }),
    );
    await screen.findByRole("heading", { name: "Recording detail" });
    await screen.findByText('"Maya Chen"');
    expect(screen.getByRole("button", { name: "Baseline" })).toBeTruthy();
  });

  it("sends POST JSON, headers and repeated query parameters without accidental row submission", async () => {
    mount();
    const user = await createProject();
    await user.click(
      screen.getByRole("button", { name: /POST.*\/echo.*Send a JSON payload/ }),
    );
    const editor = screen.getByLabelText("JSON request body");
    await user.clear(editor);
    await user.paste('{"message":"from-ui","active":false}');
    await user.click(screen.getByRole("button", { name: "Headers" }));
    await user.type(screen.getByLabelText("Header key 1"), "X-Demo");
    await user.type(screen.getByLabelText("Header value 1"), "client");
    await user.click(screen.getByRole("button", { name: "Add row" }));
    await user.click(
      screen.getByRole("button", { name: "Remove Header row 2" }),
    );
    expect(calls.filter((c) => c.path.endsWith("/requests/send")).length).toBe(
      0,
    );
    await user.click(screen.getByRole("button", { name: "Parameters" }));
    await user.type(screen.getByLabelText("Parameter key 1"), "tag");
    await user.type(screen.getByLabelText("Parameter value 1"), "a");
    await user.click(screen.getByRole("button", { name: "Add row" }));
    await user.type(screen.getByLabelText("Parameter key 2"), "tag");
    await user.type(screen.getByLabelText("Parameter value 2"), "b");
    await user.click(screen.getByRole("button", { name: "Send request" }));
    expect(calls.filter((c) => c.path.endsWith("/requests/send"))).toHaveLength(
      0,
    );
    await user.click(
      screen.getByRole("button", { name: "Confirm send request" }),
    );
    await screen.findByText('"from-ui"');
    const call = calls.find((c) => c.path.endsWith("/requests/send"))!;
    expect(call.body).toMatchObject({
      method: "POST",
      endpoint_path: "/echo",
      headers: { "X-Demo": "client" },
      query_parameters: { tag: ["a", "b"] },
      body: { message: "from-ui", active: false },
    });
  });

  it("rejects invalid JSON without sending and shows backend errors", async () => {
    mount();
    const user = await createProject();
    await user.click(screen.getByRole("button", { name: "Body" }));
    await user.click(screen.getByLabelText("JSON request body"));
    await user.paste("{invalid");
    await user.click(screen.getByRole("button", { name: "Send request" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "not valid JSON",
    );
    expect(calls.filter((c) => c.path.endsWith("/requests/send")).length).toBe(
      0,
    );
    await user.clear(screen.getByLabelText("JSON request body"));
    vi.mocked(fetch).mockResolvedValueOnce(
      json({ detail: "Target origin is not allowlisted." }, 403),
    );
    await user.click(screen.getByRole("button", { name: "Send request" }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "not allowlisted",
      ),
    );
  });

  it("edits project settings and switches to another project with a clean request workspace", async () => {
    mount();
    const user = await createProject();
    await user.click(
      within(screen.getByRole("navigation")).getByRole("link", {
        name: /Projects/,
      }),
    );
    await user.click(screen.getByRole("button", { name: "Edit Commerce API" }));
    const dialog = screen.getByRole("dialog");
    const input = within(dialog).getByLabelText("Project name");
    await user.clear(input);
    await user.type(input, "Commerce v1");
    await user.click(
      within(dialog).getByRole("button", { name: "Save project" }),
    );
    await screen.findByRole("heading", { name: "Request workspace" });
    expect(projects[0].name).toBe("Commerce v1");
    await user.click(screen.getByRole("button", { name: "New project" }));
    await user.type(
      within(screen.getByRole("dialog")).getByLabelText("Project name"),
      "Other project",
    );
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Create project",
      }),
    );
    await screen.findByRole("heading", { name: "Request workspace" });
    await user.selectOptions(
      screen.getByLabelText("Selected project"),
      "project-1",
    );
    expect(
      (screen.getByLabelText("Selected project") as HTMLSelectElement).value,
    ).toBe("project-1");
    expect(screen.getByText("No response yet")).toBeTruthy();
  });
});

it("blocks unsafe request numbers before serialization can alter them", async () => {
  mount();
  const user = await createProject();
  await user.click(screen.getByRole("button", { name: "Body" }));
  await user.click(screen.getByLabelText("JSON request body"));
  await user.paste('{"value":1e999}');
  expect((await screen.findByRole("alert")).textContent).toContain(
    "safe range",
  );
  expect(
    (screen.getByRole("button", { name: "Send request" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(calls.filter((c) => c.path.endsWith("/requests/send"))).toHaveLength(
    0,
  );
});
it("allows cancelling a potentially mutating request without executing it", async () => {
  mount();
  const user = await createProject();
  await user.selectOptions(screen.getByLabelText("HTTP method"), "DELETE");
  await user.click(screen.getByRole("button", { name: "Send request" }));
  expect(
    screen.getByRole("heading", { name: "Confirm API request" }),
  ).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(calls.filter((c) => c.path.endsWith("/requests/send"))).toHaveLength(
    0,
  );
});
