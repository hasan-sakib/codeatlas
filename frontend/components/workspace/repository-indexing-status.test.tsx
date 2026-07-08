import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { RepositoryIndexingStatus } from "@/components/workspace/repository-indexing-status";

function jsonResponse(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("RepositoryIndexingStatus", () => {
  it("shows the initial status immediately without polling if already terminal", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <RepositoryIndexingStatus workspaceId="w1" repositoryId="r1" initialStatus="ready" />,
    );

    expect(screen.getByText("ready")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("polls the BFF proxy route and updates status until it reaches a terminal state", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ status: "indexing" }))
      .mockResolvedValueOnce(jsonResponse({ status: "ready" }));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <RepositoryIndexingStatus workspaceId="w1" repositoryId="r1" initialStatus="pending" />,
    );

    expect(screen.getByText("pending")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.getByText("indexing")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/backend/workspaces/w1/repositories/r1");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.getByText("ready")).toBeInTheDocument();

    // Terminal state reached — no further polling.
    const callCountAtTerminal = fetchMock.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(fetchMock.mock.calls.length).toBe(callCountAtTerminal);
  }, 10000);

  it("keeps polling and does not crash when a fetch call fails transiently", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("network error"))
      .mockResolvedValueOnce(jsonResponse({ status: "ready" }));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <RepositoryIndexingStatus workspaceId="w1" repositoryId="r1" initialStatus="indexing" />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(screen.getByText("ready")).toBeInTheDocument();
  }, 10000);
});
