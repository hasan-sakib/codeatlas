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
    const { container } = render(
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

    // "create_app" now legitimately appears twice: the symbol badge and
    // a syntax-highlighted token inside the code block — both expected.
    expect(screen.getAllByText("create_app").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("dense")).toBeInTheDocument();
    // Syntax highlighting tokenizes the code into multiple <span>s (one
    // per keyword/identifier), so the text is no longer a single node —
    // toHaveTextContent checks the concatenated content instead.
    expect(container).toHaveTextContent("def create_app(): ...");
  });

  it("syntax-highlights code for a recognized file extension", () => {
    const { container } = render(
      <CitationCard
        filePath="app/main.py"
        startLine={1}
        endLine={5}
        score={0.5}
        text="def create_app(): ..."
      />,
    );

    // react-syntax-highlighter tokenizes into several <span>s; a plain
    // <pre><code> fallback would only ever produce a single text node.
    expect(container.querySelectorAll("code span").length).toBeGreaterThan(1);
  });

  it("falls back to a plain <pre><code> block for an unrecognized extension", () => {
    const { container } = render(
      <CitationCard
        filePath="app/data.unknownext"
        startLine={1}
        endLine={2}
        score={0.5}
        text="some raw content"
      />,
    );

    expect(container.querySelector("pre code")).toHaveTextContent("some raw content");
    expect(container.querySelectorAll("code span").length).toBe(0);
  });
});
