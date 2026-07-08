"use client";

import { useTransition } from "react";
import { deleteConversationAction } from "@/lib/actions/conversations";
import { Button } from "@/components/ui/button";

export function DeleteConversationButton({
  workspaceId,
  conversationId,
}: {
  workspaceId: string;
  conversationId: string;
}) {
  const [pending, startTransition] = useTransition();

  return (
    <Button
      variant="ghost"
      size="sm"
      disabled={pending}
      onClick={() => {
        if (!confirm("Delete this conversation?")) return;
        startTransition(() => {
          deleteConversationAction(workspaceId, conversationId);
        });
      }}
    >
      {pending ? "Deleting…" : "Delete"}
    </Button>
  );
}
