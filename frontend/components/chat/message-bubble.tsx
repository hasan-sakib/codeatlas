import { cn } from "@/lib/utils";
import type { Citation, MessageRole } from "@/lib/types";
import { CitationCard } from "@/components/chat/citation-card";

export interface MessageBubbleProps {
  role: MessageRole;
  content: string;
  citations?: Citation[];
}

export function MessageBubble({ role, content, citations }: MessageBubbleProps) {
  const isUser = role === "user";
  return (
    <div className={cn("flex flex-col gap-2", isUser ? "items-end" : "items-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-lg px-4 py-2 text-sm whitespace-pre-wrap",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted",
        )}
      >
        {content || (isUser ? "" : "…")}
      </div>
      {citations && citations.length > 0 ? (
        <div className="flex w-full max-w-[85%] flex-col gap-1.5">
          {citations.map((citation) => (
            <CitationCard
              key={citation.chunk_id}
              filePath={citation.file_path}
              startLine={citation.start_line}
              endLine={citation.end_line}
              score={citation.score}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
