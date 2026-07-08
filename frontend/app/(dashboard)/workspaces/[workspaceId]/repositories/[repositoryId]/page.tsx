import { notFound } from "next/navigation";
import { requireSession } from "@/lib/dal";
import { authedJson, ApiError } from "@/lib/backend";
import type { Repository } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RepositoryIndexingStatus } from "@/components/workspace/repository-indexing-status";
import { DeleteRepositoryButton } from "@/components/workspace/delete-repository-button";

export default async function RepositoryDetailPage({
  params,
}: {
  params: Promise<{ workspaceId: string; repositoryId: string }>;
}) {
  const { workspaceId, repositoryId } = await params;
  const session = await requireSession();

  let repository: Repository;
  try {
    repository = await authedJson<Repository>(
      `/workspaces/${workspaceId}/repositories/${repositoryId}`,
      session.accessToken,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="truncate text-2xl font-semibold">{repository.git_url}</h1>
        <p className="text-muted-foreground mt-1 text-sm">Default branch: {repository.default_branch ?? "—"}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Indexing status</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <RepositoryIndexingStatus
            workspaceId={workspaceId}
            repositoryId={repositoryId}
            initialStatus={repository.status}
          />
          <dl className="text-muted-foreground grid grid-cols-2 gap-y-1 text-sm">
            <dt>Last indexed commit</dt>
            <dd className="text-foreground truncate">{repository.last_indexed_commit_sha ?? "—"}</dd>
            <dt>Registered</dt>
            <dd className="text-foreground">{new Date(repository.created_at).toLocaleString()}</dd>
          </dl>
        </CardContent>
      </Card>

      <div>
        <DeleteRepositoryButton workspaceId={workspaceId} repositoryId={repositoryId} />
      </div>
    </div>
  );
}
