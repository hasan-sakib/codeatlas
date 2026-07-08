import Link from "next/link";
import { notFound } from "next/navigation";
import { requireSession } from "@/lib/dal";
import { authedJson, ApiError } from "@/lib/backend";
import type { Repository, Workspace } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CreateRepositoryForm } from "@/components/workspace/create-repository-form";
import { RepositoryStatusBadge } from "@/components/workspace/repository-status-badge";

export default async function WorkspaceDetailPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  const session = await requireSession();

  let workspace: Workspace;
  let repositories: Repository[];
  try {
    [workspace, repositories] = await Promise.all([
      authedJson<Workspace>(`/workspaces/${workspaceId}`, session.accessToken),
      authedJson<Repository[]>(`/workspaces/${workspaceId}/repositories`, session.accessToken),
    ]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold">{workspace.name}</h1>
        {workspace.description ? (
          <p className="text-muted-foreground mt-1 text-sm">{workspace.description}</p>
        ) : null}
      </div>

      <div className="flex gap-3">
        <Button
          variant="outline"
          nativeButton={false}
          render={<Link href={`/workspaces/${workspace.id}/search`} />}
        >
          Search this workspace
        </Button>
        <Button
          variant="outline"
          nativeButton={false}
          render={<Link href={`/workspaces/${workspace.id}/conversations`} />}
        >
          Conversations
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Register a repository</CardTitle>
        </CardHeader>
        <CardContent>
          <CreateRepositoryForm workspaceId={workspace.id} />
        </CardContent>
      </Card>

      <div>
        <h2 className="mb-3 text-lg font-medium">Repositories</h2>
        <div className="flex flex-col gap-2">
          {repositories.map((repository) => (
            <Link
              key={repository.id}
              href={`/workspaces/${workspace.id}/repositories/${repository.id}`}
            >
              <Card className="hover:bg-accent/50 transition-colors">
                <CardHeader className="flex-row items-center justify-between">
                  <CardTitle className="truncate text-sm font-normal">
                    {repository.git_url ?? repository.local_path}
                  </CardTitle>
                  <RepositoryStatusBadge status={repository.status} />
                </CardHeader>
              </Card>
            </Link>
          ))}
          {repositories.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              No repositories registered yet — add one above.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
