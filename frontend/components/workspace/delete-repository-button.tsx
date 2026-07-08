"use client";

import { useTransition } from "react";
import { deleteRepositoryAction } from "@/lib/actions/workspaces";
import { Button } from "@/components/ui/button";

export function DeleteRepositoryButton({
  workspaceId,
  repositoryId,
}: {
  workspaceId: string;
  repositoryId: string;
}) {
  const [pending, startTransition] = useTransition();

  return (
    <Button
      variant="destructive"
      size="sm"
      disabled={pending}
      onClick={() => {
        if (!confirm("Delete this repository and all of its indexed data?")) return;
        startTransition(() => {
          deleteRepositoryAction(workspaceId, repositoryId);
        });
      }}
    >
      {pending ? "Deleting…" : "Delete repository"}
    </Button>
  );
}
