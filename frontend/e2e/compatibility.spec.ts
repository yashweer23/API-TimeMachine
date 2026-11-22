import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
const v1 = process.env.E2E_TARGET_URL || "http://sample-api:8001";
const v2 = process.env.E2E_REPLAY_TARGET_URL || "http://sample-api-v2:8001";
test("assess policies, inspect evidence, preserve history and download reports", async ({
  page,
  request,
}) => {
  const created = await request.post("/api/projects", {
    data: { name: `Compatibility ${Date.now()}`, base_url: v1 },
  });
  expect(created.status()).toBe(201);
  const project = await created.json();
  const captured = await request.post(
    `/api/projects/${project.id}/requests/send`,
    { data: { endpoint_path: "/compatibility/required-removed" } },
  );
  expect(captured.status()).toBe(201);
  const original = await captured.json();
  const replay = await request.post(`/api/recordings/${original.id}/replay`, {
    data: { target_base_url: v2, name: "Compatibility browser run" },
  });
  expect(replay.status()).toBe(201);
  const session = await replay.json();
  expect(
    (
      await request.post(`/api/replay-sessions/${session.id}/compare`, {
        data: {},
      })
    ).status(),
  ).toBe(200);
  await page.goto(`/compatibility?project=${project.id}&session=${session.id}`);
  await page
    .getByRole("button", { name: "Analyze session", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Potential compatibility issues",
      exact: true,
    }),
  ).toBeVisible();
  const historical = page.url();
  await page.locator(".compatibility-policies > summary").click();
  await page.getByLabel("Policies JSON").fill(
    JSON.stringify({
      endpoints: [
        {
          method: "GET",
          endpoint_path: "/compatibility/required-removed",
          required_json_paths: ["/id"],
        },
      ],
    }),
  );
  await page
    .getByRole("button", { name: "Save policies", exact: true })
    .click();
  await expect(
    page.getByText(/Policies saved. Select Analyze session/),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Analyze session", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Incompatible with configured contract",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByLabel("Classification", { exact: true })
    .selectOption("confirmed_breaking");
  await page.getByLabel("Severity", { exact: true }).selectOption("high");
  await page
    .getByRole("heading", { name: "Required JSON path is absent", exact: true })
    .click();
  await expect(
    page.getByText("contract.required_path", { exact: true }),
  ).toBeVisible();
  const diff = page.getByRole("link", {
    name: "Open saved Phase 3 difference",
  });
  await expect(diff).toHaveAttribute("href", /difference=/);
  const jsonDownload = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download JSON" }).click();
  const jsonFile = await jsonDownload;
  const data = JSON.parse(await readFile((await jsonFile.path())!, "utf8"));
  expect(data.summary.confirmed_breaking).toBe(1);
  expect(data.omitted_findings).toBe(0);
  const htmlDownload = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download HTML" }).click();
  const htmlFile = await htmlDownload;
  expect(await readFile((await htmlFile.path())!, "utf8")).toContain(
    "Frozen policies and comparison rules",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.goto(historical);
  await expect(
    page.getByRole("heading", {
      name: "Potential compatibility issues",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(/older policies\/comparison rules/),
  ).toBeVisible();
  expect(
    await (await request.get(`/api/recordings/${original.id}`)).json(),
  ).toEqual(original);
});
