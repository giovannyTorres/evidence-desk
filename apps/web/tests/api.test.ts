import { describe, expect, it, vi, afterEach } from "vitest";
import { api, ApiError, consumeEvents } from "../src/lib/api";
afterEach(() => vi.unstubAllGlobals());
describe("streaming contract", () => {
  it("preserves split UTF-8 and fragmented SSE events", async () => {
    const bytes = new TextEncoder().encode(
      'event: token\r\ndata: {"text":"Política de viajes"}\r\n\r\nevent: done\ndata: {"message_id":"a"}\n\n',
    );
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        for (const byte of bytes) c.enqueue(new Uint8Array([byte]));
        c.close();
      },
    });
    const events: unknown[] = [];
    await consumeEvents(stream, (event, data) => events.push({ event, data }));
    expect(events).toEqual([
      { event: "token", data: { text: "Política de viajes" } },
      { event: "done", data: { message_id: "a" } },
    ]);
  });
  it("surfaces server errors without raw gateway contents", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("<private gateway error>", { status: 503 }),
        ),
    );
    await expect(api("/documents")).rejects.toMatchObject({ status: 503 });
    await expect(api("/documents")).rejects.not.toThrow("private gateway");
  });
  it("keeps authorization errors actionable", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: "Please sign in again." }), {
            status: 401,
          }),
        ),
    );
    await expect(api("/me")).rejects.toBeInstanceOf(ApiError);
  });
});
