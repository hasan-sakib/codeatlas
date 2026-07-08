"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import type { Repository, RepositoryStatus } from "@/lib/types";
import { RepositoryStatusBadge } from "@/components/workspace/repository-status-badge";

const POLL_INTERVAL_MS = 3000;
const TERMINAL_STATUSES: RepositoryStatus[] = ["ready", "failed"];

/** Polls rather than streams: the backend has no indexing-progress SSE
 * endpoint yet (only repository CRUD exists — the `/jobs/{id}/events`
 * endpoint from the original design was never built), so this is the
 * only signal available. It stops polling once the status reaches a
 * terminal state. */
export function RepositoryIndexingStatus({
  workspaceId,
  repositoryId,
  initialStatus,
}: {
  workspaceId: string;
  repositoryId: string;
  initialStatus: RepositoryStatus;
}) {
  const [status, setStatus] = useState<RepositoryStatus>(initialStatus);

  useEffect(() => {
    if (TERMINAL_STATUSES.includes(status)) return;

    let cancelled = false;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/backend/workspaces/${workspaceId}/repositories/${repositoryId}`);
        if (!res.ok) return;
        const repository = (await res.json()) as Repository;
        if (!cancelled) setStatus(repository.status);
      } catch {
        // Transient network error — the next tick will retry.
      }
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [status, workspaceId, repositoryId]);

  return (
    <div className="flex items-center gap-2">
      <RepositoryStatusBadge status={status} />
      {status === "indexing" || status === "pending" ? (
        <span className="text-muted-foreground flex items-center gap-1.5 text-sm">
          <Loader2 className="size-3.5 animate-spin" />
          Checking every few seconds…
        </span>
      ) : null}
    </div>
  );
}
