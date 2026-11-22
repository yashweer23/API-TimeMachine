import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
const v1 = process.env.E2E_TARGET_URL || "http://sample-api:8001";
const v2 = process.env.E2E_REPLAY_TARGET_URL || "http://sample-api-v2:8001";
test("complete release journey through project, baseline, replay, assessment and report", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const projectName = `Sample API Regression Testing ${Date.now()}`;
  await page.goto("/");
  await page
    .getByRole("button", { name: "New project", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Project name").fill(projectName);
  await dialog.getByLabel("Target base URL").fill(v1);
  await dialog
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await page.getByLabel("Endpoint path").fill("/users/1");
  await page.getByRole("button", { name: "Details", exact: true }).click();
  await page.getByLabel("New recording name").fill("Release user baseline");
  await page.getByRole("button", { name: "Send request", exact: true }).click();
  await expect(page.getByRole("region", { name: "Response" })).toContainText(
    "200",
  );
  await page
    .getByRole("button", { name: "Mark baseline", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Baseline", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Replay", exact: true })
    .click();
  await page.getByLabel("Select Release user baseline").check();
  await page.getByLabel("Replay target base URL").fill(v2);
  await page.getByLabel("Session name").fill("Final release demo");
  await page.getByRole("button", { name: "Run replay", exact: true }).click();
  await expect(
    page.getByRole("article", { name: "Original recording" }),
  ).toContainText("Maya");
  await expect(
    page.getByRole("article", { name: "Replayed response" }),
  ).toContainText("full_name");
  await page
    .getByRole("button", { name: "Compare & analyze", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Potential compatibility issues",
      exact: true,
    }),
  ).toBeVisible();
  await page.locator(".compatibility-policies > summary").click();
  await page.getByLabel("Policies JSON").fill(
    JSON.stringify({
      endpoints: [
        {
          method: "GET",
          endpoint_path: "/users/1",
          required_json_paths: ["/data/name"],
          expected_types: { "/data/id": "integer" },
        },
      ],
    }),
  );
  await page
    .getByRole("button", { name: "Save policies", exact: true })
    .click();
  await expect(page.getByText(/Policies saved/)).toBeVisible();
  await page
    .getByRole("button", { name: "Compare & analyze", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Incompatible with configured contract",
      exact: true,
    }),
  ).toBeVisible();
  const historicalURL = page.url();
  await page.reload();
  await expect(
    page.getByRole("heading", {
      name: "Incompatible with configured contract",
      exact: true,
    }),
  ).toBeVisible();
  const nextDownload = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download JSON", exact: true }).click();
  const file = await nextDownload;
  const report = JSON.parse(await readFile((await file.path())!, "utf8"));
  expect(report.summary.confirmed_breaking).toBe(2);
  expect(report.metadata_snapshot.project_name).toBe(projectName);
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Reports", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Reports", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Final release demo/ }).first(),
  ).toBeVisible();
  await page.goto(historicalURL);
  await expect(
    page.getByRole("link", { name: "Download HTML", exact: true }),
  ).toBeVisible();
  if (process.env.SCREENSHOT_DIR)
    await page.screenshot({
      path: `${process.env.SCREENSHOT_DIR}/release-compatibility.png`,
      fullPage: true,
    });
  expect(errors).toEqual([]);
});
