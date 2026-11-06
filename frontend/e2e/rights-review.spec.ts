import { expect, test } from "@playwright/test";

test("local narrative rights desk explains the snapshot review workflow", async ({ page }) => {
  await page.goto("/admin/rights");
  await expect(page.getByRole("heading", { name: "Narrative-use review" })).toBeVisible();
  await expect(page.getByLabel("Operator email")).toBeVisible();
  await expect(page.getByText(/not legal advice/i)).toBeVisible();
  await expect(page.getByText(/Enter the configured local operator email/)).toBeVisible();
  await expect(page.getByRole("link", { name: "← Film intake" })).toHaveAttribute("href", "/admin/intake");
});
