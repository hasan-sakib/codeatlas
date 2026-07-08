import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatPanel } from "@/components/chat/chat-panel";
import { useStreamingStore } from "@/lib/stores/streaming-store";

const { refreshMock, toastErrorMock, streamSSEMock } = vi.hoisted(() => ({
  refreshMock: vi.fn(),
  toastErrorMock: vi.fn(),
  streamSSEMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: refreshMock }),
}));

vi.mock("sonner", () => ({
  toast: { error: toastErrorMock },
}));

vi.mock("@/lib/sse-client", () => ({
  streamSSE: (...args: unknown[]) => streamSSEMock(...args),
}));

beforeEach(() => {
  refreshMock.mockClear();
  toastErrorMock.mockClear();
  streamSSEMock.mockReset();
  useStreamingStore.getState().reset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ChatPanel", () => {
  it("renders finalized history messages from props", () => {
    render(
      <ChatPanel
        workspaceId="w1"
        conversationId="c1"
        initialMessages={[
          {
            id: "m1",
            conversation_id: "c1",
            role: "user",
            content: "hello",
            citations: [],
            token_count: 1,
            created_at: null,
          },
          {
            id: "m2",
            conversation_id: "c1",
            role: "assistant",
            content: "hi there",
            citations: [],
            token_count: 2,
            created_at: null,
          },
        ]}
      />,
    );

    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText("hi there")).toBeInTheDocument();
  });

  it("shows the optimistic user bubble and streamed partial text while mid-stream", async () => {
    let releaseSecondToken!: () => void;
    const gate = new Promise<void>((resolve) => {
      releaseSecondToken = resolve;
    });

    streamSSEMock.mockReturnValue(
      (async function* () {
        yield { name: "token", data: { text: "Hel" } };
        await gate; // pause so the test can assert deterministic mid-stream state
        yield { name: "token", data: { text: "lo!" } };
        yield { name: "done", data: { message_id: null } };
      })(),
    );

    const user = userEvent.setup();
    render(<ChatPanel workspaceId="w1" conversationId="c1" initialMessages={[]} />);

    await user.type(screen.getByPlaceholderText(/ask about this codebase/i), "hi");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(streamSSEMock).toHaveBeenCalledWith(
      "/api/backend/workspaces/w1/conversations/c1/messages",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ content: "hi" }),
      }),
    );

    await waitFor(() => expect(useStreamingStore.getState().partialText).toBe("Hel"));
    expect(screen.getByText("hi")).toBeInTheDocument();
    expect(screen.getByText("Hel")).toBeInTheDocument();

    releaseSecondToken();

    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
    expect(useStreamingStore.getState().isStreaming).toBe(false);
    expect(useStreamingStore.getState().partialText).toBe("");
  });

  it("shows a toast and still resets state when the stream throws", async () => {
    streamSSEMock.mockImplementation(async function* () {
      throw new Error("connection lost");
    });

    const user = userEvent.setup();
    render(<ChatPanel workspaceId="w1" conversationId="c1" initialMessages={[]} />);

    await user.type(screen.getByPlaceholderText(/ask about this codebase/i), "hi");
    await user.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalled());
    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
    expect(useStreamingStore.getState().isStreaming).toBe(false);
  });

  it("does not submit an empty message", async () => {
    const user = userEvent.setup();
    render(<ChatPanel workspaceId="w1" conversationId="c1" initialMessages={[]} />);

    const sendButton = screen.getByRole("button", { name: /send/i });
    expect(sendButton).toBeDisabled();

    await user.click(sendButton);
    expect(streamSSEMock).not.toHaveBeenCalled();
  });
});
