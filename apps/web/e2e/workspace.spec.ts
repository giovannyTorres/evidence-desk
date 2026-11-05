import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
const screenshots = "../../docs/screenshots";
async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Welcome to your desk." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(
    page.getByRole("button", { name: "Ask your documents" }),
  ).toBeVisible();
}
test("document → example question → answer → source, real persisted conversation", async ({
  page,
}) => {
  await mkdir(screenshots, { recursive: true });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Welcome to your desk." }),
  ).toBeVisible();
  await page.screenshot({
    path: `${screenshots}/01-sign-in.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.locator(".suggestion").first()).toBeVisible();
  await page.screenshot({
    path: `${screenshots}/02-workspace.png`,
    fullPage: true,
  });
  const question = await page.locator(".suggestion").first().innerText();
  await page.locator(".suggestion").first().click();
  await expect(page.locator(".citation-card").first()).toBeVisible({
    timeout: 30000,
  });
  await expect(
    page.getByText("Example response", { exact: true }),
  ).toBeVisible();
  await page.locator(".citation-card").first().click();
  await expect(
    page.getByRole("complementary", { name: "Source evidence" }),
  ).toBeVisible();
  await expect(page.locator("blockquote")).not.toBeEmpty();
  await page.screenshot({
    path: `${screenshots}/03-answer-and-source.png`,
    fullPage: true,
  });
  await page.reload();
  await expect(page.locator(".history-item").first()).toBeVisible();
  await page.locator(".history-item").first().click();
  await expect(page.locator(".citation-card").first()).toBeVisible();
  expect(question.length).toBeGreaterThan(5);
});
test("library accepts a real upload and displays processing, with responsive layout", async ({
  page,
}) => {
  await signIn(page);
  await page.getByRole("button", { name: /Document library/ }).click();
  await expect(
    page.getByRole("heading", { name: "Document library." }),
  ).toBeVisible();
  const filename = `browser-check-${Date.now()}.md`;
  await page
    .getByLabel("Upload document file")
    .setInputFiles({
      name: filename,
      mimeType: "text/markdown",
      buffer: Buffer.from(
        "# Browser validation\n\nThis original synthetic note confirms that browser uploads reach the persistent processing worker.",
      ),
    });
  await expect(page.getByText(filename, { exact: false }).first()).toBeVisible({
    timeout: 20000,
  });
  await page.screenshot({
    path: `${screenshots}/04-document-library.png`,
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Ask your documents" }).click();
  await page.screenshot({
    path: `${screenshots}/05-mobile-workspace.png`,
    fullPage: true,
  });
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(hasHorizontalOverflow).toBe(false);
});
test("free-form DEMO explains LIVE and keeps keyboard focus visible", async ({
  page,
}) => {
  await signIn(page);
  await page
    .getByLabel("Ask a question about your documents")
    .fill("An arbitrary new question");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.getByRole("status")).toContainText("require LIVE mode");
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .first()
    .focus();
  await expect(
    page.getByRole("button", { name: "New conversation", exact: true }).first(),
  ).toBeFocused();
});
