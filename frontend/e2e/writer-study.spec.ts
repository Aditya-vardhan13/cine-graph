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

  const firstAlternatives = page.getByRole("navigation", { name: "Source passages for Batman Begins" });
  await expect(firstAlternatives.getByText(/Passage 1 of/)).toBeVisible();
  await firstAlternatives.getByRole("button", { name: "Next passage for Batman Begins" }).click();
  await expect(firstAlternatives.getByText(/Passage 2 of/)).toBeVisible();

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

  const archiveEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON" }).click();
  const archive = await archiveEvent;
  const stream = await archive.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  await page.getByLabel("Restore writer studies from JSON").setInputFiles({
    name: "cinegraph-writer-decisions.json", mimeType: "application/json", buffer: Buffer.concat(chunks),
  });
  await expect(page.getByRole("status").filter({ hasText: "1 study restored from this file." })).toBeVisible();
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

test("film profile opens the writer desk with that film selected", async ({ page, request }) => {
  const films = await request.get("http://127.0.0.1:18001/api/v1/films?q=dark%20knight&limit=1");
  expect(films.ok()).toBeTruthy();
  const film = (await films.json())[0];
  await page.goto(`/films/${film.id}`);
  await page.getByRole("link", { name: "Study this film as a writer" }).click();
  await expect(page).toHaveURL(/\?study=.*#compare/);
  await expect(page.locator(".comparison-slots").getByText("The Dark Knight", { exact: true })).toBeVisible();
});
