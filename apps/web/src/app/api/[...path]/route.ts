import type { NextRequest } from "next/server";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const MAX_BODY = 6 * 1024 * 1024;
/** Same-origin gateway. The upstream is operator-configured, never taken from user input. */
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  const headers = new Headers();
  for (const name of [
    "cookie",
    "content-type",
    "origin",
    "x-request-id",
    "accept",
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const upstream = new URL(
    `${process.env.API_URL ?? "http://localhost:8101"}/api/${path.map(encodeURIComponent).join("/")}`,
  );
  upstream.search = request.nextUrl.search;
  let body: Uint8Array | undefined;
  if (!["GET", "HEAD"].includes(request.method) && request.body) {
    if (Number(request.headers.get("content-length") ?? 0) > MAX_BODY)
      return Response.json(
        { detail: "Choose a file smaller than 5 MB." },
        { status: 413 },
      );
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    for (;;) {
      const next = await reader.read();
      if (next.done) break;
      size += next.value.length;
      if (size > MAX_BODY) {
        await reader.cancel();
        return Response.json(
          { detail: "Choose a file smaller than 5 MB." },
          { status: 413 },
        );
      }
      chunks.push(next.value);
    }
    body = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      body.set(chunk, offset);
      offset += chunk.length;
    }
  }
  try {
    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body: body as BodyInit | undefined,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(180000)]),
    });
    const outgoing = new Headers();
    for (const name of [
      "content-type",
      "cache-control",
      "x-request-id",
      "x-correlation-id",
      "content-disposition",
      "x-accel-buffering",
    ]) {
      const value = response.headers.get(name);
      if (value) outgoing.set(name, value);
    }
    for (const cookie of response.headers.getSetCookie())
      outgoing.append("set-cookie", cookie);
    outgoing.set("Cache-Control", "no-store");
    return new Response(response.body, {
      status: response.status,
      headers: outgoing,
    });
  } catch {
    return Response.json(
      {
        detail:
          "The workspace service is temporarily unavailable. Please try again.",
      },
      { status: 502 },
    );
  }
}
export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
  proxy as OPTIONS,
};
