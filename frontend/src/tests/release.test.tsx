import { afterEach, it, expect, vi } from "vitest";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  cleanup,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { Recordings, RecordingDetail } from "../pages/Recordings";
import { ReportDownloads } from "../components/compatibility/ReportDownloads";
import type { Recording } from "../types";
const project = {
  id: "owner",
  name: "Owner project",
  base_url: "http://sample-api:8001",
  description: null,
  created_at: "2026-11-19T00:00:00Z",
  updated_at: "2026-11-19T00:00:00Z",
};
const record: Recording = {
  id: "r1",
  project_id: "owner",
  name: "Reference",
  method: "GET",
  base_url: project.base_url,
  endpoint_path: "/users/1",
  query_parameters: {},
  request_headers: {},
  request_body: null,
  request_body_present: false,
  response_status: 200,
  response_headers: {},
  response_body: { id: 1 },
  response_body_kind: "json",
  content_type: "application/json",
  duration_ms: 2,
  captured_at: project.created_at,
  environment_label: null,
  is_baseline: false,
  execution_error: null,
};
const response = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
it("keeps recording filters on the server and encodes literal search safely", async () => {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      return response({ items: [record], total: 1, limit: 20, offset: 0 });
    }),
  );
  render(
    <MemoryRouter>
      <Recordings project={project} />
    </MemoryRouter>,
  );
  await screen.findByText("Reference");
  fireEvent.change(screen.getByLabelText("Search recordings"), {
    target: { value: "100%_ /users" },
  });
  await userEvent.selectOptions(
    screen.getByLabelText("HTTP method filter"),
    "GET",
  );
  await waitFor(() =>
    expect(
      urls.some(
        (url) =>
          url.includes("search=100%25_%20%2Fusers") &&
          url.includes("method=GET"),
      ),
    ).toBe(true),
  );
});
it("synchronizes the owning project when opening a recording directly", async () => {
  const onProject = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response(record)),
  );
  render(
    <MemoryRouter initialEntries={["/recordings/r1"]}>
      <Routes>
        <Route
          path="/recordings/:id"
          element={<RecordingDetail onProject={onProject} />}
        />
      </Routes>
    </MemoryRouter>,
  );
  await waitFor(() => expect(onProject).toHaveBeenCalledWith("owner"));
  expect(
    screen
      .getByRole("link", { name: "Back to recordings" })
      .getAttribute("href"),
  ).toBe("/recordings?project=owner");
});
it("shows export errors in the workspace without claiming a download", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      response({ detail: "Report exceeds the export limit." }, 413),
    ),
  );
  render(<ReportDownloads runId="run1" engineVersion="compatibility-v1" />);
  await userEvent.click(screen.getByRole("link", { name: "Download HTML" }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Report exceeds the export limit",
  );
  expect(
    screen
      .getByRole("link", { name: "Download HTML" })
      .getAttribute("aria-disabled"),
  ).toBe("false");
});
it("downloads actual report bytes with a fixed safe filename", async () => {
  const make = vi.fn(() => "blob:report"),
    revoke = vi.fn(),
    BaseURL = URL;
  vi.stubGlobal(
    "URL",
    class extends BaseURL {
      static createObjectURL = make;
      static revokeObjectURL = revoke;
    },
  );
  const clicks: string[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    clicks.push(this.download);
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => response({ summary: { confirmed_breaking: 1 } })),
  );
  render(<ReportDownloads runId="run1" engineVersion="compatibility-v1" />);
  await userEvent.click(screen.getByRole("link", { name: "Download JSON" }));
  await waitFor(() => expect(clicks).toEqual(["compatibility-run1.json"]));
  expect(make).toHaveBeenCalledTimes(1);
});
