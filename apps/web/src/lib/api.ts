export type Mode = "DEMO" | "LIVE";
export interface Config {
  mode: Mode;
  ready: boolean;
  missing: string[];
  provider?: string;
  model?: string;
}
export interface User {
  id: string;
  email: string;
  org: string;
  name?: string;
}
export interface Document {
  id: string;
  title: string;
  status: string;
  version: number;
  filename: string;
  error?: string | null;
}
export interface Citation {
  chunk_id: string;
  document_id: string;
  version: number;
  location: string;
  excerpt: string;
  title: string;
}
export interface Scenario {
  id: string;
  question: string;
}
export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations?: Citation[];
}
export interface Conversation {
  id: string;
  title: string;
  messages?: Message[];
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, {
    credentials: "same-origin",
    ...init,
    headers,
  });
  if (!response.ok) {
    let message = `Request could not be completed (${response.status}). Please try again.`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* Safe generic error for non-JSON gateways. */
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
/** Parse SSE incrementally, preserving UTF-8 and events split over arbitrary network chunks. */
export async function consumeEvents(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const drain = () => {
    buffer = buffer.replace(/\r\n/g, "\n");
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) onEvent(event, JSON.parse(data.join("\n")));
    }
  };
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      drain();
    }
    buffer += decoder.decode();
    drain();
  } finally {
    reader.releaseLock();
  }
}
