import { SearchPanel } from "@/components/search/search-panel";

export default async function SearchPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  return <SearchPanel workspaceId={workspaceId} />;
}
