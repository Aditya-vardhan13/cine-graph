import { expect, test } from "@playwright/test";

test("local narrative rights desk explains the snapshot review workflow", async ({ page }) => {
  await page.goto("/admin/rights");
  await expect(page.getByRole("heading", { name: "Narrative-use review" })).toBeVisible();
  await expect(page.getByLabel("Operator email")).toBeVisible();
  await expect(page.getByText(/not legal advice/i)).toBeVisible();
  await expect(page.getByText(/Enter the configured local operator email/)).toBeVisible();
  await expect(page.getByRole("link", { name: "← Film intake" })).toHaveAttribute("href", "/admin/intake");
});

test("rights desk filters its local queue by film title and review state", async ({ page, request }) => {
  const health = await request.get("http://127.0.0.1:18001/health");
  expect(health.ok(), "Start the isolated integration API before the browser test").toBeTruthy();
  await page.goto("/admin/rights");
  await page.getByLabel("Operator email").fill("adityavk1310@gmail.com");
  await expect(page.getByText(/matching source snapshots/)).toBeVisible();
  await page.getByLabel("Film title").fill("The Dark Knight");
  await page.getByRole("button", { name: "Apply title filter" }).click();
  await expect(page.locator(".rights-card").first().locator("h2")).toContainText("The Dark Knight");
  await page.getByLabel("Film title").fill("Definitely No CineGraph Film");
  await page.getByRole("button", { name: "Apply title filter" }).click();
  await expect(page.getByText("0 of 0 matching source snapshots · purpose: semantic indexing and model input")).toBeVisible();
  await page.getByLabel("Review state").selectOption("unreviewed");
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByText(/of \d+ matching source snapshots/)).toBeVisible();
});

test("film intake labels the boundary between capture and indexing", async ({ page }) => {
  await page.goto("/admin/intake");
  await expect(page.getByRole("heading", { name: "Add films to the research corpus" })).toBeVisible();
  await expect(page.getByText(/Capture complete.*does not mean rights approval, evidence indexing, or embeddings are complete/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Review narrative-use permissions →" })).toHaveAttribute("href", "/admin/rights");
});
