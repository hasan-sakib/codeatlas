import { describe, expect, it, vi, afterEach } from "vitest";
import { streamSSE } from "@/lib/sse-client";

function streamFromChunks(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let index = 0;
  return new ReadableStream({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index]));
        index += 1;
      } else {
        controller.close();
      }
    },
  });
}

function mockFetchWithStream(body: ReadableStream<Uint8Array>, ok = true, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok,
      status,
      body,
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("streamSSE", () => {
  it("parses a single complete event in one chunk", async () => {
    mockFetchWithStream(streamFromChunks(['event: token\ndata: {"text":"hi"}\n\n']));

    const events = [];
    for await (const event of streamSSE("/x", {})) {
      events.push(event);
    }

    expect(events).toEqual([{ name: "token", data: { text: "hi" } }]);
  });

  it("reassembles an event split across multiple stream reads", async () => {
    // The "\n\n" terminator itself is split across chunk boundaries — a
    // real occurrence over a network stream, not just a theoretical case.
    mockFetchWithStream(
      streamFromChunks(['event: token\ndata: {"te', 'xt":"hello"}\n', '\nevent: done\ndata: {}\n\n']),
    );

    const events = [];
    for await (const event of streamSSE("/x", {})) {
      events.push(event);
    }

    expect(events).toEqual([
      { name: "token", data: { text: "hello" } },
      { name: "done", data: {} },
    ]);
  });

  it("parses multiple events delivered in one chunk", async () => {
    mockFetchWithStream(
      streamFromChunks([
        'event: citation\ndata: {"chunk_id":"c1","file_path":"a.py","start_line":1,"end_line":2,"score":0.9}\n\nevent: done\ndata: {"message_id":null}\n\n',
      ]),
    );

    const events = [];
    for await (const event of streamSSE("/x", {})) {
      events.push(event);
    }

    expect(events).toHaveLength(2);
    expect(events[0].name).toBe("citation");
    expect(events[1].name).toBe("done");
  });

  it("skips a block with no event name", async () => {
    mockFetchWithStream(streamFromChunks(['data: {"text":"orphan"}\n\nevent: done\ndata: {}\n\n']));

    const events = [];
    for await (const event of streamSSE("/x", {})) {
      events.push(event);
    }

    expect(events).toEqual([{ name: "done", data: {} }]);
  });

  it("throws when the response is not ok", async () => {
    mockFetchWithStream(streamFromChunks([]), false, 500);

    await expect(async () => {
      const iterator = streamSSE("/x", {})[Symbol.asyncIterator]();
      await iterator.next();
    }).rejects.toThrow("SSE request failed with status 500");
  });
});
