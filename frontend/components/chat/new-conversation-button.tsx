"use client";

import { useTransition } from "react";
import { createConversationAction } from "@/lib/actions/conversations";
import { Button } from "@/components/ui/button";

export function NewConversationButton({ workspaceId }: { workspaceId: string }) {
  const [pending, startTransition] = useTransition();

  return (
    <Button
      disabled={pending}
      onClick={() => startTransition(() => createConversationAction(workspaceId))}
    >
      {pending ? "Starting…" : "New conversation"}
    </Button>
  );
}
