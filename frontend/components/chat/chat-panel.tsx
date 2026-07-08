"use client";

import { useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { streamSSE } from "@/lib/sse-client";
import { useStreamingStore } from "@/lib/stores/streaming-store";
import type {
  CitationEventPayload,
  DoneEventPayload,
  ErrorEventPayload,
  Message,
  TokenEventPayload,
} from "@/lib/types";
import { MessageBubble } from "@/components/chat/message-bubble";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function ChatPanel({
  workspaceId,
  conversationId,
  initialMessages,
}: {
  workspaceId: string;
  conversationId: string;
  initialMessages: Message[];
}) {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [pendingUserContent, setPendingUserContent] = useState<string | null>(null);
  const [isSending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);

  const { isStreaming, partialText, citations, startStreaming, appendToken, addCitation, finishStreaming, reset } =
    useStreamingStore();

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = input.trim();
    if (!content || isStreaming) return;

    setInput("");
    setPendingUserContent(content);
    startStreaming();

    try {
      const events = streamSSE(
        `/api/backend/workspaces/${workspaceId}/conversations/${conversationId}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
        },
      );

      for await (const event of events) {
        if (event.name === "token") {
          appendToken((event.data as TokenEventPayload).text);
        } else if (event.name === "citation") {
          addCitation(event.data as CitationEventPayload);
        } else if (event.name === "error") {
          const payload = event.data as ErrorEventPayload;
          toast.error(payload.detail ?? payload.title);
        } else if (event.name === "done") {
          void (event.data as DoneEventPayload);
        }
      }
    } catch {
      toast.error("Lost connection to the assistant. Please try again.");
    } finally {
      finishStreaming();
      startTransition(() => {
        router.refresh();
      });
      setPendingUserContent(null);
      reset();
    }
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto">
        {initialMessages.map((message) => (
          <MessageBubble
            key={message.id}
            role={message.role}
            content={message.content}
            citations={message.citations}
          />
        ))}
        {pendingUserContent !== null ? (
          <MessageBubble role="user" content={pendingUserContent} />
        ) : null}
        {isStreaming || (isSending && partialText) ? (
          <MessageBubble
            role="assistant"
            content={partialText}
            citations={citations.map((c) => ({ ...c }))}
          />
        ) : null}
      </div>

      <form ref={formRef} onSubmit={handleSubmit} className="flex gap-2">
        <Textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              formRef.current?.requestSubmit();
            }
          }}
          placeholder="Ask about this codebase…"
          disabled={isStreaming}
          className="min-h-11 resize-none"
          rows={1}
        />
        <Button type="submit" disabled={isStreaming || !input.trim()}>
          Send
        </Button>
      </form>
    </div>
  );
}
