import { test, expect } from "@playwright/test";
const v1 = process.env.E2E_TARGET_URL || "http://sample-api:8001";
const v2 = process.env.E2E_REPLAY_TARGET_URL || "http://sample-api-v2:8001";
test("compare saved responses, inspect changes, ignore a timestamp and preserve history", async ({
  page,
  request,
}) => {
  const created = await request.post("/api/projects", {
    data: { name: `Comparison ${Date.now()}`, base_url: v1 },
  });
  expect(created.status()).toBe(201);
  const project = await created.json();
  const capture = await request.post(
    `/api/projects/${project.id}/requests/send`,
    {
      data: {
        endpoint_path: "/regression/timestamp",
        name: "Timestamp reference",
      },
    },
  );
  expect(capture.status()).toBe(201);
  const recording = await capture.json();
  const replay = await request.post(`/api/recordings/${recording.id}/replay`, {
    data: { target_base_url: v2, name: "Browser comparison run" },
  });
  expect(replay.status()).toBe(201);
  const session = await replay.json();
  await page.goto(`/comparisons?project=${project.id}&session=${session.id}`);
  await page
    .getByRole("button", { name: "Compare session", exact: true })
    .click();
  await page
    .getByRole("link", {
      name: /GET.*regression\/timestamp.*Timestamp reference/,
    })
    .click();
  await expect(
    page.getByRole("region", { name: "Comparison summary" }),
  ).toContainText("1 detected differences");
  const explorer = page.getByRole("region", { name: "Difference explorer" });
  await explorer.getByLabel("Filter changes").selectOption("value_changed");
  await explorer.getByLabel("Search difference paths").fill("/generated_at");
  await explorer
    .getByRole("button", {
      name: "Inspect body /generated_at Value changed",
      exact: true,
    })
    .click();
  await expect(explorer).toContainText("2026-11-10T10:00:00Z");
  await expect(explorer).toContainText("2026-11-11T10:00:00Z");
  await expect(
    page
      .getByRole("article", { name: "Replayed highlighted response" })
      .locator('[data-current="true"]'),
  ).toContainText("Value changed");
  const historicalURL = page.url();
  await page.locator(".comparison-rules > summary").click();
  await page.getByLabel("Ignored JSON paths").fill("/generated_at");
  await page
    .getByRole("button", { name: "Save comparison rules", exact: true })
    .click();
  await expect(
    page.getByText(/This historical comparison uses older settings/),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Recalculate with current rules",
      exact: true,
    })
    .click();
  await expect(
    page.getByRole("region", { name: "Comparison summary" }),
  ).toContainText("0 detected differences");
  await page.reload();
  await expect(
    page.getByText("No differences under these rules", { exact: true }),
  ).toBeVisible();
  await page.goto(historicalURL);
  await expect(
    page.getByRole("region", { name: "Comparison summary" }),
  ).toContainText("1 detected differences");
  await expect(
    page.getByText(/This historical comparison uses older settings/),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("region", { name: "Difference explorer" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  if (process.env.SCREENSHOT_DIR)
    await page.screenshot({
      path: `${process.env.SCREENSHOT_DIR}/comparison-mobile.png`,
      fullPage: true,
    });
  const unchanged = await request.get(`/api/recordings/${recording.id}`);
  expect(await unchanged.json()).toEqual(recording);
});
