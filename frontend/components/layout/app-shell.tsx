import { WorkspaceSidebar } from "@/components/workspace/workspace-sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-1">
      <WorkspaceSidebar />
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </div>
  );
}
