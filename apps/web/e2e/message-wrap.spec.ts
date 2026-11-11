import { test, expect } from "@playwright/test";

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`long questions and answers wrap at ${viewport.width}px`, async ({ page }) => {
    const question = `https://example.org/${"longidentifier".repeat(35)}`;
    const answer = `Source: https://example.org/${"longanswer".repeat(55)}\n${"A long response with normal words. ".repeat(30)}`;
    await page.setViewportSize(viewport);
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/config") return route.fulfill({ json: { mode: "LIVE", ready: true, missing: [] } });
      if (path === "/api/me") return route.fulfill({ json: { id: "u", email: "test@example.org", org: "test" } });
      if (path === "/api/documents" || path === "/api/scenarios") return route.fulfill({ json: [] });
      if (path === "/api/conversations" && route.request().method() === "POST") return route.fulfill({ json: { id: "c", title: "test" } });
      if (path === "/api/conversations") return route.fulfill({ json: [] });
      if (path === "/api/conversations/c/messages") return route.fulfill({ contentType: "text/event-stream", body: `event: token\ndata: ${JSON.stringify({ text: answer })}\n\nevent: done\ndata: {}\n\n` });
      if (path === "/api/conversations/c") return route.fulfill({ json: { id: "c", title: "test", messages: [{ id: "q", role: "user", content: question }, { id: "a", role: "assistant", content: answer }] } });
      return route.fulfill({ status: 404 });
    });
    await page.goto("/");
    await page.getByLabel("Ask a question about your documents").fill(question);
    await page.getByRole("button", { name: "Send question" }).click();
    for (const role of ["user", "assistant"]) {
      const message = page.locator(`.message.${role} .message-content`);
      await expect(message).toBeVisible();
      await expect.poll(() => message.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
      await expect(message).toHaveCSS("overflow-wrap", "anywhere");
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}
