import type { SSEEvent, SSEEventName } from "@/lib/types";

/** Parses a `fetch` + `ReadableStream` response into SSE events. Not
 * `EventSource`-based: the chat endpoint is a POST with a JSON body,
 * which `EventSource` cannot send — it only supports GET. Buffers
 * across reads so an event split across two stream chunks (a real
 * occurrence, not just a theoretical edge case) is still parsed
 * correctly once its terminating blank line arrives. */
export async function* streamSSE(url: string, init: RequestInit): AsyncGenerator<SSEEvent> {
  const response = await fetch(url, init);
  if (!response.ok || !response.body) {
    throw new Error(`SSE request failed with status ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let separatorIndex = buffer.indexOf("\n\n");
      while (separatorIndex !== -1) {
        const rawEvent = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);
        const event = parseEventBlock(rawEvent);
        if (event) yield event;
        separatorIndex = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseEventBlock(block: string): SSEEvent | null {
  let name: SSEEventName | null = null;
  const dataLines: string[] = [];

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      name = line.slice("event:".length).trim() as SSEEventName;
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }

  if (!name || dataLines.length === 0) return null;
  try {
    return { name, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}
