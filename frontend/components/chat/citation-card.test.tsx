import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CitationCard } from "@/components/chat/citation-card";

describe("CitationCard", () => {
  it("renders the file path, line range, and score", () => {
    render(<CitationCard filePath="app/main.py" startLine={10} endLine={20} score={0.876} />);

    expect(screen.getByText("app/main.py:10-20")).toBeInTheDocument();
    expect(screen.getByText("0.88")).toBeInTheDocument();
  });

  it("omits symbol/source badges and code preview when not provided (CitationEvent shape)", () => {
    render(<CitationCard filePath="app/main.py" startLine={1} endLine={5} score={0.5} />);

    expect(screen.queryByText(/dense|sparse|fused|reranked/i)).not.toBeInTheDocument();
  });

  it("renders symbol name, source badge, and code preview when provided (SearchResultItem shape)", () => {
    render(
      <CitationCard
        filePath="app/main.py"
        startLine={1}
        endLine={5}
        score={0.5}
        symbolName="create_app"
        source="dense"
        text="def create_app(): ..."
      />,
    );

    expect(screen.getByText("create_app")).toBeInTheDocument();
    expect(screen.getByText("dense")).toBeInTheDocument();
    expect(screen.getByText("def create_app(): ...")).toBeInTheDocument();
  });
});
