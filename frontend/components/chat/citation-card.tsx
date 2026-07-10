"use client";

import { useTheme } from "next-themes";
import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter";
import bash from "react-syntax-highlighter/dist/esm/languages/prism/bash";
import go from "react-syntax-highlighter/dist/esm/languages/prism/go";
import java from "react-syntax-highlighter/dist/esm/languages/prism/java";
import javascript from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
import jsx from "react-syntax-highlighter/dist/esm/languages/prism/jsx";
import markdown from "react-syntax-highlighter/dist/esm/languages/prism/markdown";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import tsx from "react-syntax-highlighter/dist/esm/languages/prism/tsx";
import typescript from "react-syntax-highlighter/dist/esm/languages/prism/typescript";
import yaml from "react-syntax-highlighter/dist/esm/languages/prism/yaml";
import oneDark from "react-syntax-highlighter/dist/esm/styles/prism/one-dark";
import oneLight from "react-syntax-highlighter/dist/esm/styles/prism/one-light";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { detectLanguageFromPath } from "@/lib/detect-language";

// Deliberately NOT called at module scope: verified directly against a
// real production build that Next.js's bundler tree-shook top-level
// `registerLanguage(...)` calls (and their grammar imports) away
// entirely — nothing "uses" their return value, so a bundler that
// doesn't specifically know these calls are side-effectful drops them,
// and every code block silently rendered as plain unhighlighted text
// with zero errors. Calling this from inside the component body, where
// it's unambiguously reachable live code, survives tree-shaking; the
// `registered` guard keeps it a one-time cost across renders.
let registered = false;
function ensureLanguagesRegistered(): void {
  if (registered) return;
  SyntaxHighlighter.registerLanguage("python", python);
  SyntaxHighlighter.registerLanguage("javascript", javascript);
  SyntaxHighlighter.registerLanguage("jsx", jsx);
  SyntaxHighlighter.registerLanguage("typescript", typescript);
  SyntaxHighlighter.registerLanguage("tsx", tsx);
  SyntaxHighlighter.registerLanguage("go", go);
  SyntaxHighlighter.registerLanguage("java", java);
  SyntaxHighlighter.registerLanguage("json", json);
  SyntaxHighlighter.registerLanguage("yaml", yaml);
  SyntaxHighlighter.registerLanguage("markdown", markdown);
  SyntaxHighlighter.registerLanguage("bash", bash);
  registered = true;
}

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
  ensureLanguagesRegistered();
  const { resolvedTheme } = useTheme();
  const language = detectLanguageFromPath(filePath);

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
          language ? (
            <SyntaxHighlighter
              language={language}
              style={resolvedTheme === "dark" ? oneDark : oneLight}
              customStyle={{ margin: 0, borderRadius: "var(--radius-md)" }}
              codeTagProps={{ className: "text-xs" }}
            >
              {text}
            </SyntaxHighlighter>
          ) : (
            <pre className="bg-muted overflow-x-auto rounded-md p-2 text-xs">
              <code>{text}</code>
            </pre>
          )
        ) : null}
      </CardContent>
    </Card>
  );
}
