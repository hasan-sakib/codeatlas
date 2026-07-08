import { Badge } from "@/components/ui/badge";
import type { RepositoryStatus } from "@/lib/types";

const VARIANT_BY_STATUS: Record<RepositoryStatus, "secondary" | "default" | "destructive" | "outline"> = {
  pending: "outline",
  indexing: "default",
  ready: "secondary",
  failed: "destructive",
};

export function RepositoryStatusBadge({ status }: { status: RepositoryStatus }) {
  return (
    <Badge variant={VARIANT_BY_STATUS[status]} className="capitalize">
      {status}
    </Badge>
  );
}
