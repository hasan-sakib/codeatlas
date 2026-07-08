import Link from "next/link";
import { requireSession } from "@/lib/dal";
import { authedJson } from "@/lib/backend";
import type { Workspace } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CreateWorkspaceForm } from "@/components/workspace/create-workspace-form";

export default async function WorkspacesPage() {
  const session = await requireSession();
  const workspaces = await authedJson<Workspace[]>("/workspaces", session.accessToken);

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold">Workspaces</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Each workspace holds its own indexed repositories, conversations, and search index.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">New workspace</CardTitle>
        </CardHeader>
        <CardContent>
          <CreateWorkspaceForm />
        </CardContent>
      </Card>

      <div className="flex flex-col gap-2">
        {workspaces.map((workspace) => (
          <Link key={workspace.id} href={`/workspaces/${workspace.id}`}>
            <Card className="hover:bg-accent/50 transition-colors">
              <CardHeader>
                <CardTitle className="text-base">{workspace.name}</CardTitle>
              </CardHeader>
              {workspace.description ? (
                <CardContent className="text-muted-foreground text-sm">
                  {workspace.description}
                </CardContent>
              ) : null}
            </Card>
          </Link>
        ))}
        {workspaces.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            You don&apos;t have any workspaces yet — create one above.
          </p>
        ) : null}
      </div>
    </div>
  );
}
