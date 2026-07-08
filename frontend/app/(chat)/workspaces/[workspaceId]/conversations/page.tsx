import Link from "next/link";
import { requireSession } from "@/lib/dal";
import { authedJson } from "@/lib/backend";
import type { Conversation, Envelope } from "@/lib/types";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { NewConversationButton } from "@/components/chat/new-conversation-button";

export default async function ConversationsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const session = await requireSession();
  const envelope = await authedJson<Envelope<Conversation[]>>(
    `/workspaces/${workspaceId}/conversations`,
    session.accessToken,
  );

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Conversations</h1>
        <NewConversationButton workspaceId={workspaceId} />
      </div>

      <div className="flex flex-col gap-2">
        {envelope.data.map((conversation) => (
          <Link
            key={conversation.id}
            href={`/workspaces/${workspaceId}/conversations/${conversation.id}`}
          >
            <Card className="hover:bg-accent/50 transition-colors">
              <CardHeader>
                <CardTitle className="text-sm font-normal">
                  {conversation.title ?? `Conversation started ${new Date(conversation.created_at).toLocaleString()}`}
                </CardTitle>
              </CardHeader>
            </Card>
          </Link>
        ))}
        {envelope.data.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            No conversations yet — start one above.
          </p>
        ) : null}
      </div>
    </div>
  );
}
