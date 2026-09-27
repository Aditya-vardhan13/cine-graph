import { expect, test } from "@playwright/test";

test("writer can search, compare, pin evidence, and export a study", async ({ page, request }) => {
  const health = await request.get("http://127.0.0.1:18001/health");
  expect(health.ok(), "Start the isolated integration API before the browser test").toBeTruthy();

  await page.goto("/");
  const search = page.getByRole("textbox", { name: "Search comparison films" });
  await search.fill("Batman Begins");
  await page.getByRole("button", { name: /Batman Begins.*select/ }).click();
  await search.fill("The Dark Knight");
  await page.getByRole("button", { name: /The Dark Knight.*select/ }).click();

  await page.getByRole("textbox", { name: "Your writing question" }).fill(
    "How does becoming a public symbol change Batman's moral choices?",
  );
  await page.getByRole("button", { name: "Build evidence comparison" }).click();
  await expect(page.getByRole("heading", { name: /Batman Begins.*The Dark Knight/ })).toBeVisible();
  await expect(page.getByText("Additional source context", { exact: false })).toBeVisible();

  const pinButtons = page.getByRole("button", { name: "Pin as evidence +" });
  await pinButtons.first().click();
  await pinButtons.first().click();
  await page.getByRole("textbox", { name: /How Batman Begins handles it/ }).fill("The symbol provokes escalation.");
  await page.getByRole("textbox", { name: /How The Dark Knight handles it/ }).fill("He accepts blame to preserve hope.");
  await page.getByRole("textbox", { name: "The meaningful difference" }).fill("One starts the public role; the other bears its cost.");
  await page.getByRole("textbox", { name: "Your creative decision" }).fill("Make my protagonist choose who receives public credit.");
  await page.getByRole("button", { name: "Save this study" }).click();
  await expect(page.getByText("Make my protagonist choose who receives public credit.")).toBeVisible();

  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export readable notes" }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("cinegraph-writer-studies.md");
});

test("unsupported question abstains without losing selected films", async ({ page, request }) => {
  const health = await request.get("http://127.0.0.1:18001/health");
  expect(health.ok(), "Start the isolated integration API before the browser test").toBeTruthy();

  await page.goto("/");
  const search = page.getByRole("textbox", { name: "Search comparison films" });
  await search.fill("Batman Begins");
  await page.getByRole("button", { name: /Batman Begins.*select/ }).click();
  await search.fill("The Dark Knight");
  await page.getByRole("button", { name: /The Dark Knight.*select/ }).click();
  await page.getByRole("textbox", { name: "Your writing question" }).fill(
    "Which private off-the-record meeting changed the film's ending?",
  );
  await page.getByRole("button", { name: "Build evidence comparison" }).click();
  await expect(page.getByRole("heading", { name: "Current sources cannot substantiate this question." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Refine the question" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Try another film" })).toBeVisible();
  await expect(page.getByText("Batman Begins", { exact: true }).first()).toBeVisible();
});
