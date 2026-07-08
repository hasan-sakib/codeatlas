import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

interface CitationCardProps {
  filePath: string;
  startLine: number;
  endLine: number;
  score: number;
  symbolName?: string | null;
  source?: string | null;
  text?: string | null;
}

/** Renders both shapes the backend produces: a streamed CitationEvent
 * (file_path/start_line/end_line/score only) and a SearchResultItem
 * (which additionally carries symbol_name/source/text) — symbolName,
 * source, and text are therefore all optional here. */
export function CitationCard({
  filePath,
  startLine,
  endLine,
  score,
  symbolName,
  source,
  text,
}: CitationCardProps) {
  return (
    <Card className="gap-2 py-3">
      <CardContent className="flex flex-col gap-1.5 px-3">
        <div className="flex items-center justify-between gap-2">
          <code className="truncate text-xs font-medium">
            {filePath}:{startLine}-{endLine}
          </code>
          <Badge variant="outline" className="shrink-0">
            {score.toFixed(2)}
          </Badge>
        </div>
        {symbolName || source ? (
          <div className="flex items-center gap-1.5">
            {symbolName ? (
              <Badge variant="secondary" className="font-mono">
                {symbolName}
              </Badge>
            ) : null}
            {source ? (
              <Badge variant="outline" className="capitalize">
                {source}
              </Badge>
            ) : null}
          </div>
        ) : null}
        {text ? (
          <pre className="bg-muted overflow-x-auto rounded-md p-2 text-xs">
            <code>{text}</code>
          </pre>
        ) : null}
      </CardContent>
    </Card>
  );
}
