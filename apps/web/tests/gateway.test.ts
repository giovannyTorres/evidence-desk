import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "../src/app/api/[...path]/route";
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
describe("same-origin gateway boundaries", () => {
  it("keeps the destination operator-controlled and does not follow redirects", async () => {
    vi.stubEnv("API_URL", "http://api:8000");
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok"));
    vi.stubGlobal("fetch", fetchMock);
    const request = new NextRequest(
      "http://localhost:3101/api/documents?target=http://internal.invalid",
      {
        headers: {
          cookie: "evidence_session=abc",
          origin: "http://localhost:3101",
        },
      },
    );
    await GET(request, { params: Promise.resolve({ path: ["documents"] }) });
    expect(fetchMock.mock.calls[0][0].origin).toBe("http://api:8000");
    expect(fetchMock.mock.calls[0][1].redirect).toBe("manual");
    expect(fetchMock.mock.calls[0][1].headers.get("cookie")).toBe(
      "evidence_session=abc",
    );
  });
  it("rejects oversized requests before reaching the API", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const request = new NextRequest("http://localhost:3101/api/documents", {
      method: "POST",
      headers: { "content-length": String(12 * 1024 * 1024) },
      body: "oversized",
    });
    const response = await POST(request, {
      params: Promise.resolve({ path: ["documents"] }),
    });
    expect(response.status).toBe(413);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("never exposes upstream transport errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("private-token internal-host")),
    );
    const response = await GET(
      new NextRequest("http://localhost:3101/api/config"),
      { params: Promise.resolve({ path: ["config"] }) },
    );
    expect(response.status).toBe(502);
    expect(await response.text()).not.toContain("private-token");
  });
});
