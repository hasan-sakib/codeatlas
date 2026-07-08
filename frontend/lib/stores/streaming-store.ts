import { create } from "zustand";
import type { CitationEventPayload } from "@/lib/types";

/** The only client-side global state in the app. Everything else
 * (workspace lists, conversation history, repository lists) is
 * server-rendered and refetched via `router.refresh()`; this store
 * exists only because SSE-streamed tokens/citations are inherently
 * client-only and too transient to round-trip through the server. */
interface StreamingState {
  isStreaming: boolean;
  partialText: string;
  citations: CitationEventPayload[];
  error: string | null;
  startStreaming: () => void;
  appendToken: (text: string) => void;
  addCitation: (citation: CitationEventPayload) => void;
  setError: (message: string) => void;
  finishStreaming: () => void;
  reset: () => void;
}

export const useStreamingStore = create<StreamingState>((set) => ({
  isStreaming: false,
  partialText: "",
  citations: [],
  error: null,
  startStreaming: () => set({ isStreaming: true, partialText: "", citations: [], error: null }),
  appendToken: (text) => set((state) => ({ partialText: state.partialText + text })),
  addCitation: (citation) => set((state) => ({ citations: [...state.citations, citation] })),
  setError: (message) => set({ error: message, isStreaming: false }),
  finishStreaming: () => set({ isStreaming: false }),
  reset: () => set({ isStreaming: false, partialText: "", citations: [], error: null }),
}));
