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
  await page.screenshot({ animations: "disabled",
    path: `${screenshots}/01-sign-in.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.locator(".suggestion").first()).toBeVisible();
  await page.screenshot({ animations: "disabled",
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
  await page.screenshot({ animations: "disabled",
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
  await page.screenshot({ animations: "disabled",
    path: `${screenshots}/04-document-library.png`,
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Ask your documents" }).click();
  await page.screenshot({ animations: "disabled",
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

test("audit: durable extraction failure, recovery, and empty library search", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: /Document library/ }).click();
  const filename = `audit-malformed-${Date.now()}.pdf`;
  await page.getByLabel("Upload document file").setInputFiles({name: filename, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7\ninvalid body")});
  const row = page.locator(".document-row").filter({hasText: filename});
  await expect(row.locator(".status-chip")).toHaveText("error", {timeout: 20000});
  await expect(row.getByRole("button", {name: `Retry ${filename}`})).toBeVisible();
  await page.screenshot({ animations: "disabled",path: `${screenshots}/audit-extraction-error.png`, fullPage: true});
  await Promise.all([
    page.waitForResponse(response => response.url().endsWith("/retry") && response.status() === 200),
    row.getByRole("button", {name: `Retry ${filename}`}).click(),
  ]);
  await expect.poll(async () => {
    const response = await page.request.get("/api/documents");
    const documents = await response.json();
    return documents.find((document: { filename: string }) => document.filename === filename)?.status;
  }, {timeout: 20000}).toBe("error");
  await expect(row.locator(".status-chip")).toHaveText("error", {timeout: 20000});
  page.once("dialog", dialog => dialog.accept());
  await row.getByRole("button", {name: `Delete ${filename}`} ).click();
  await expect(row).toHaveCount(0);
  await page.getByPlaceholder("Find a document…").fill("there-is-no-document-with-this-title");
  await expect(page.getByRole("heading", {name: "No documents match"})).toBeVisible();
});

test("audit: truncated transport is visible and a new conversation recovers", async ({ page }) => {
  await signIn(page);
  await page.route("**/api/conversations/*/messages", async route => {
    await route.fulfill({status:200, contentType:"text/event-stream", body:'event: token\ndata: {"text":"Incomplete fixture"}\n\n'});
  });
  await page.locator(".suggestion").first().click();
  await expect(page.getByRole("alert").filter({hasText: "ended early"})).toBeVisible();
  await page.screenshot({ animations: "disabled",path:`${screenshots}/audit-stream-error.png`,fullPage:true});
  await page.unroute("**/api/conversations/*/messages");
  await page.getByRole("button",{name:"New conversation",exact:true}).first().click();
  await page.locator(".suggestion").first().click();
  await expect(page.locator(".citation-card").first()).toBeVisible({timeout:20000});
});

test("audit: confirmed LIVE mode does not prefill DEMO identities", async ({page}) => {
  await page.route("**/api/config", route => route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({mode:"LIVE",ready:false,missing:["OPENAI_API_KEY"],provider:"openai",model:"gpt-4.1-mini"})}));
  await page.goto("/");
  await expect(page.locator(".mode-pill")).toContainText("LIVE");
  await expect(page.getByLabel("Email address")).toHaveValue("");
  await expect(page.getByLabel("Password",{exact:true})).toHaveValue("");
  await expect(page.locator(".demo-access")).toHaveCount(0);
  await page.getByLabel("Email address").fill("reviewer@portfolio.example");
  await expect(page.getByLabel("Email address")).toHaveValue("reviewer@portfolio.example");
});

test("audit: configuration outage is UNKNOWN and retry recovers mode", async ({page}) => {
  await page.route("**/api/config", route => route.fulfill({status:503,contentType:"application/json",body:JSON.stringify({detail:"Configuration temporarily unavailable"})}));
  await page.goto("/");
  await expect(page.locator(".mode-pill")).toContainText("MODE UNKNOWN");
  await expect(page.getByLabel("Email address")).toHaveValue("");
  await expect(page.getByLabel("Password",{exact:true})).toHaveValue("");
  await expect(page.getByRole("button",{name:"Open workspace"})).toBeDisabled();
  await expect(page.locator(".demo-access")).toHaveCount(0);
  await page.screenshot({animations:"disabled",path:`${screenshots}/audit-mode-unavailable.png`,fullPage:true});
  await page.unroute("**/api/config");
  await page.getByRole("button",{name:"Retry connection"}).click();
  await expect(page.locator(".mode-pill")).toContainText("DEMO");
  await expect(page.getByLabel("Email address")).toHaveValue("analyst@aurora.example");
  await expect(page.getByRole("button",{name:"Open workspace"})).toBeEnabled();
});
