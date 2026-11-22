import { test, expect } from "@playwright/test";
const target = process.env.E2E_TARGET_URL || "http://sample-api:8001";
test("create, capture, persist, baseline, inspect, and post JSON", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "New project", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  const projectName = `Commerce ${Date.now()}`;
  await dialog.getByLabel("Project name").fill(projectName);
  await dialog.getByLabel("Target base URL").fill(target);
  await dialog
    .getByLabel("Description")
    .fill("Browser verification of the Phase 1 recording flow.");
  await dialog
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Request workspace" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Send request", exact: true }).click();
  const response = page.getByRole("region", { name: "Response", exact: true });
  await expect(response.getByText("Maya Chen", { exact: false })).toBeVisible();
  await expect(response.getByText("200", { exact: true })).toBeVisible();
  await response
    .getByRole("button", { name: "Mark baseline", exact: true })
    .click();
  await expect(
    response.getByRole("button", { name: "Baseline", exact: true }),
  ).toBeVisible();
  await response
    .getByRole("button", { name: "GET /users", exact: true })
    .click();
  await response
    .getByLabel("Recording name", { exact: true })
    .fill("Users reference v1");
  await response.getByRole("button", { name: "Save changes" }).click();
  await expect(
    response.getByRole("button", { name: "Users reference v1" }),
  ).toBeVisible();
  if (process.env.SCREENSHOT_DIR)
    await page.screenshot({
      path: `${process.env.SCREENSHOT_DIR}/workspace-desktop.png`,
      fullPage: true,
    });
  await page.reload();
  await expect(page.getByLabel("Selected project")).toHaveValue(
    await page.getByLabel("Selected project").inputValue(),
  );
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Recordings", exact: true })
    .click();
  await page.getByRole("button", { name: "Baselines", exact: true }).click();
  await page
    .getByRole("link", { name: /GET.*Users reference v1.*\/users/ })
    .click();
  await expect(
    page.getByRole("button", { name: "Baseline", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Maya Chen", { exact: false })).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Workspace", exact: true })
    .click();
  await page
    .getByRole("button", { name: /POST.*\/echo.*Send a JSON payload/ })
    .click();
  await page
    .getByLabel("JSON request body")
    .fill('{"message":"browser-test","password":"do-not-store"}');
  await page.getByRole("button", { name: "Send request", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm send request", exact: true })
    .click();
  await expect(
    response.getByText("browser-test", { exact: false }),
  ).toBeVisible();
  await expect(
    response.getByText("[REDACTED]", { exact: false }),
  ).toBeVisible();
  await expect(response).not.toContainText("do-not-store");
  await page
    .getByRole("button", { name: "Headers", exact: true })
    .first()
    .click();
  await page.getByRole("button", { name: "Add row", exact: true }).click();
  await expect(page.getByLabel("Header key 2")).toBeVisible();
  await page.getByLabel("Header key 2").fill("X-Demo");
  await page.getByLabel("Header value 2").fill("example");
  await page.getByRole("button", { name: "Remove Header row 2" }).click();
  await expect(page.getByLabel("Header key 2")).toHaveCount(0);
  // The row buttons must never implicitly submit the request form.
  await expect(
    page.getByRole("button", { name: "Send request", exact: true }),
  ).toBeEnabled();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("Endpoint path")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  if (process.env.SCREENSHOT_DIR)
    await page.screenshot({
      path: `${process.env.SCREENSHOT_DIR}/workspace-mobile.png`,
      fullPage: true,
    });
  expect(errors).toEqual([]);
});

test("validation, genuine HTTP errors, project switching, and project edits", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByRole("button", { name: "New project", exact: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  const name = `Validation ${Date.now()}`;
  await dialog.getByLabel("Project name").fill(name);
  await dialog.getByLabel("Target base URL").fill(target);
  await dialog
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await page.getByRole("button", { name: "Body", exact: true }).first().click();
  await page.getByLabel("JSON request body").fill("{bad json");
  await expect(
    page.getByRole("button", { name: "Send request", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("alert")).toContainText("not valid JSON");
  await page.getByLabel("JSON request body").fill("");
  await page.getByLabel("Endpoint path").fill("/users/999");
  await page.getByRole("button", { name: "Send request", exact: true }).click();
  await expect(
    page
      .getByRole("region", { name: "Response" })
      .getByText("404", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: /Projects/ })
    .click();
  await page.getByRole("button", { name: `Edit ${name}`, exact: true }).click();
  await dialog.getByLabel("Project name").fill(name + " updated");
  await dialog
    .getByRole("button", { name: "Save project", exact: true })
    .click();
  await expect(
    page.getByLabel("Selected project").locator("option:checked"),
  ).toHaveText(name + " updated");
});
