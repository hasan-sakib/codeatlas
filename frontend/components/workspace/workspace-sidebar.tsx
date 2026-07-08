import Link from "next/link";
import { requireSession } from "@/lib/dal";
import { authedJson } from "@/lib/backend";
import type { Workspace } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { LogoutButton } from "@/components/auth/logout-button";

export async function WorkspaceSidebar() {
  const session = await requireSession();
  const workspaces = await authedJson<Workspace[]>("/workspaces", session.accessToken);

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r p-4">
      <Link href="/workspaces" className="mb-6 text-lg font-semibold">
        CodeAtlas
      </Link>

      <div className="flex-1 overflow-y-auto">
        <p className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
          Workspaces
        </p>
        <nav className="flex flex-col gap-1">
          {workspaces.map((workspace) => (
            <Link
              key={workspace.id}
              href={`/workspaces/${workspace.id}`}
              className="hover:bg-accent rounded-md px-2 py-1.5 text-sm"
            >
              {workspace.name}
            </Link>
          ))}
          {workspaces.length === 0 ? (
            <p className="text-muted-foreground px-2 py-1.5 text-sm">No workspaces yet.</p>
          ) : null}
        </nav>
        <Button
          variant="outline"
          size="sm"
          className="mt-3 w-full"
          nativeButton={false}
          render={<Link href="/workspaces" />}
        >
          New workspace
        </Button>
      </div>

      <div className="mt-4 flex items-center justify-between border-t pt-4">
        <span className="text-muted-foreground truncate text-sm">{session.email}</span>
        <LogoutButton />
      </div>
    </aside>
  );
}
