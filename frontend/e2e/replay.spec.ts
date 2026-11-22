import { test, expect } from "@playwright/test";

const v1 = process.env.E2E_TARGET_URL || "http://sample-api:8001";
const v2 = process.env.E2E_REPLAY_TARGET_URL || "http://sample-api-v2:8001";

test("replay v1 captures against v2, confirm mutations, inspect both snapshots, and reopen history", async ({
  page,
  request,
}) => {
  const projectResponse = await request.post("/api/projects", {
    data: { name: `Replay ${Date.now()}`, base_url: v1 },
  });
  expect(projectResponse.status()).toBe(201);
  const project = await projectResponse.json();
  const sourcePayloads = [
    { method: "GET", endpoint_path: "/users/1", name: "User reference" },
    {
      method: "POST",
      endpoint_path: "/echo",
      name: "Echo reference",
      body: { message: "browser replay" },
    },
  ];
  const originals = [];
  for (const payload of sourcePayloads) {
    const response = await request.post(
      `/api/projects/${project.id}/requests/send`,
      { data: payload },
    );
    expect(response.status()).toBe(201);
    const recording = await response.json();
    expect(recording.response_status).toBe(200);
    originals.push(recording);
  }
  await page.goto(`/replay?project=${project.id}`);
  await page.getByLabel("Select User reference").check();
  await page.getByLabel("Select Echo reference").check();
  await page.getByLabel("Replay target base URL").fill(v2);
  await page.getByLabel("Session name").fill("Browser v2 run");
  await page.getByRole("button", { name: "Run replay", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("can change data");
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  const emptyHistory = await request.get(
    `/api/projects/${project.id}/replay-sessions`,
  );
  expect((await emptyHistory.json()).total).toBe(0);
  await page.getByRole("button", { name: "Run replay", exact: true }).click();
  await dialog
    .getByRole("button", { name: "Confirm and run", exact: true })
    .click();
  const original = page.getByRole("article", {
    name: "Original recording",
    exact: true,
  });
  const replayed = page.getByRole("article", {
    name: "Replayed response",
    exact: true,
  });
  await expect(replayed).toContainText('"full_name"');
  await expect(original).toContainText('"name"');
  await expect(replayed).not.toContainText('"role"');
  await page
    .getByRole("button", { name: "Inspect POST /echo", exact: true })
    .click();
  await expect(replayed).toContainText("201");
  await expect(original).toContainText("200");
  await expect(replayed).toContainText("browser replay");
  const sessionURL = page.url();
  await page.reload();
  await expect(replayed).toContainText("201");
  await page.getByRole("link", { name: "Replay history", exact: true }).click();
  await page.getByRole("link", { name: /Browser v2 run/ }).click();
  await expect(page).toHaveURL(sessionURL.split("?")[0]);
  await expect(replayed).toContainText('"full_name"');
  for (const recording of originals) {
    const persisted = await request.get(`/api/recordings/${recording.id}`);
    expect(await persisted.json()).toEqual(recording);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(original).toBeVisible();
  await expect(replayed).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  if (process.env.SCREENSHOT_DIR) {
    await page.screenshot({
      path: `${process.env.SCREENSHOT_DIR}/replay-mobile.png`,
      fullPage: true,
    });
  }
});
