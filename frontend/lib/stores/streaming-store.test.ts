import { beforeEach, describe, expect, it } from "vitest";
import { useStreamingStore } from "@/lib/stores/streaming-store";

beforeEach(() => {
  useStreamingStore.getState().reset();
});

describe("useStreamingStore", () => {
  it("starts streaming with clean state", () => {
    useStreamingStore.getState().appendToken("stale");
    useStreamingStore.getState().startStreaming();

    const state = useStreamingStore.getState();
    expect(state.isStreaming).toBe(true);
    expect(state.partialText).toBe("");
    expect(state.citations).toEqual([]);
    expect(state.error).toBeNull();
  });

  it("appendToken concatenates onto partialText", () => {
    useStreamingStore.getState().appendToken("Hello, ");
    useStreamingStore.getState().appendToken("world!");

    expect(useStreamingStore.getState().partialText).toBe("Hello, world!");
  });

  it("addCitation appends without mutating the previous array", () => {
    const citation = { chunk_id: "c1", file_path: "a.py", start_line: 1, end_line: 2, score: 0.5 };
    useStreamingStore.getState().addCitation(citation);

    expect(useStreamingStore.getState().citations).toEqual([citation]);
  });

  it("setError stops streaming and records the message", () => {
    useStreamingStore.getState().startStreaming();
    useStreamingStore.getState().setError("boom");

    const state = useStreamingStore.getState();
    expect(state.isStreaming).toBe(false);
    expect(state.error).toBe("boom");
  });

  it("finishStreaming stops streaming without touching accumulated text", () => {
    useStreamingStore.getState().startStreaming();
    useStreamingStore.getState().appendToken("done");
    useStreamingStore.getState().finishStreaming();

    const state = useStreamingStore.getState();
    expect(state.isStreaming).toBe(false);
    expect(state.partialText).toBe("done");
  });

  it("reset clears everything back to initial values", () => {
    useStreamingStore.getState().startStreaming();
    useStreamingStore.getState().appendToken("x");
    useStreamingStore.getState().addCitation({
      chunk_id: "c1",
      file_path: "a.py",
      start_line: 1,
      end_line: 2,
      score: 0.5,
    });
    useStreamingStore.getState().setError("boom");

    useStreamingStore.getState().reset();

    expect(useStreamingStore.getState()).toMatchObject({
      isStreaming: false,
      partialText: "",
      citations: [],
      error: null,
    });
  });
});
