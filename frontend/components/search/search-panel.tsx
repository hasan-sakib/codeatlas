"use client";

import { useState } from "react";
import type { SearchResultItem, Envelope } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CitationCard } from "@/components/chat/citation-card";

export function SearchPanel({ workspaceId }: { workspaceId: string }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    setIsSearching(true);
    setError(null);
    try {
      const res = await fetch(`/api/backend/workspaces/${workspaceId}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed, limit: 20 }),
      });
      if (!res.ok) {
        throw new Error(`Search failed with status ${res.status}`);
      }
      const envelope = (await res.json()) as Envelope<SearchResultItem[]>;
      setResults(envelope.data);
    } catch {
      setError("Search failed. Please try again.");
      setResults([]);
    } finally {
      setIsSearching(false);
      setHasSearched(true);
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Search</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Semantic hybrid search across this workspace&apos;s indexed code — no chat, just ranked results.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="e.g. code that validates credit card numbers"
        />
        <Button type="submit" disabled={isSearching || !query.trim()}>
          {isSearching ? "Searching…" : "Search"}
        </Button>
      </form>

      {error ? <p className="text-destructive text-sm">{error}</p> : null}

      <div className="flex flex-col gap-2">
        {results.map((result) => (
          <CitationCard
            key={result.chunk_id}
            filePath={result.file_path}
            startLine={result.start_line}
            endLine={result.end_line}
            score={result.score}
            symbolName={result.symbol_name}
            source={result.source}
            text={result.text}
          />
        ))}
        {hasSearched && !isSearching && results.length === 0 && !error ? (
          <p className="text-muted-foreground text-sm">No results found.</p>
        ) : null}
      </div>
    </div>
  );
}
