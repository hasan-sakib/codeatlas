import { notFound } from "next/navigation";
import { requireSession } from "@/lib/dal";
import { authedJson, ApiError } from "@/lib/backend";
import type { Conversation, Envelope, Message } from "@/lib/types";
import { ChatPanel } from "@/components/chat/chat-panel";
import { DeleteConversationButton } from "@/components/chat/delete-conversation-button";

export default async function ConversationDetailPage({
  params,
}: {
  params: Promise<{ workspaceId: string; conversationId: string }>;
}) {
  const { workspaceId, conversationId } = await params;
  const session = await requireSession();

  let conversation: Conversation;
  let messages: Envelope<Message[]>;
  try {
    [conversation, messages] = await Promise.all([
      authedJson<Conversation>(
        `/workspaces/${workspaceId}/conversations/${conversationId}`,
        session.accessToken,
      ),
      authedJson<Envelope<Message[]>>(
        `/workspaces/${workspaceId}/conversations/${conversationId}/messages`,
        session.accessToken,
      ),
    ]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="truncate text-xl font-semibold">
          {conversation.title ?? "Conversation"}
        </h1>
        <DeleteConversationButton workspaceId={workspaceId} conversationId={conversationId} />
      </div>
      <ChatPanel
        workspaceId={workspaceId}
        conversationId={conversationId}
        initialMessages={messages.data}
      />
    </div>
  );
}
