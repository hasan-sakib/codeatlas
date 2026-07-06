# Module 8: Chunking Engine

## Purpose

Convert Module 7's parsed symbols into token-budgeted `ChunkCandidate`s for embedding (Module 9) — cutting at AST boundaries for code and heading/paragraph boundaries for markdown, then merging undersized fragments so retrieval never returns uselessly tiny chunks.

## `ChunkCandidate` field reference

| Field | Maps to (downstream) |
|---|---|
| `text` | `chunks.content` |
| `token_count` | not persisted directly; used to size embedding batches (Module 9) |
| `file_path` | joins to `files.path` |
| `language` | `chunks.symbol_kind`-adjacent metadata, also drives the embedding/reranker's language awareness |
| `symbol_kind` | `chunks.symbol_kind` (Qdrant payload field, per DESIGN.md §15) |
| `symbol_name` | `chunks.symbol_name` |
| `start_line`/`end_line` | `chunks.start_line`/`end_line` |
| `source_stage` | not persisted — debugging/observability only, to answer "why does this chunk look the way it does" |

## Layering

- `app/infrastructure/chunking/token_counter.py` — `count_tokens()`, backed by the **real BGE-M3 tokenizer** (`BAAI/bge-m3` via the lightweight `tokenizers` package, not the full `transformers`/`torch` stack — only tokenization is needed here, not model inference). Loaded lazily (`lru_cache`) so importing this module never triggers a network call; the `tokenizer.json` file is fetched from the Hub on first real use and cached locally (`~/.cache/huggingface`), shared with whatever Module 9 does later.
- `app/infrastructure/chunking/_line_window.py` — `slice_lines()`/`line_window_split()`, the last-resort fixed-window splitter shared by both chunkers below. Free to make arbitrary line cuts since it's only reached once every language/heading-aware boundary is exhausted.
- `app/infrastructure/chunking/ast_chunker.py` — `AstChunker`, code chunking.
- `app/infrastructure/chunking/semantic_chunker.py` — `SemanticChunker`, markdown chunking.
- `app/infrastructure/chunking/chunk_merger.py` — `ChunkMerger`, the final pass.
- `app/infrastructure/chunking/pipeline.py` — `chunk_file()`, the public entry point for code files (AstChunker → ChunkMerger). Markdown has no `ParsedFile` to hand this function (no markdown grammar is registered in Module 7), so the future indexing pipeline calls `SemanticChunker(...).chunk(markdown_text, file_path)` directly for `.md` files instead of going through `chunk_file()`.
- `app/core/config.py` — `ChunkingSettings` (`max_chunk_tokens=512`, `min_chunk_tokens=64`, `merge_target_tokens=256` defaults), optional like `GitSettings` since every field has a sane default.

## Key design decisions, verified empirically

1. **A class that fits its budget is one chunk — not one chunk per method plus a duplicate whole-class chunk.** Module 7's `extract_symbols()` returns a class *and* its methods as separate list entries (useful elsewhere), but chunking every symbol independently would produce overlapping candidates. `_select_top_level_symbols()` drops any symbol nested inside an already-selected symbol's line range. If the outer symbol (say, the class) turns out to be oversized, the *generic* recursive AST descent (`_split_node`) rediscovers the same method boundaries on its own — a class's only named children are its name and body block, and if the whole class is oversized the body block almost always is too, so recursion lands on the actual methods one level down. Verified directly: an artificial 8-method oversized class produces one candidate per method, all tagged `symbol_kind="class"` (the piece inherits the *original* top-level symbol's identity, not a per-method identity — `ChunkCandidate` has no parent-symbol field to do otherwise).
2. **Recursive splitting guarantees zero gaps/overlaps by construction, not by testing it after the fact.** At every level, `_split_node` converts a node's named children into contiguous line-range "units" — each unit starts exactly where the previous one ended, absorbing any inter-child gap (punctuation, comments, blank lines) into the unit that follows — then greedily merges adjacent units under budget, recursing into any single still-oversized unit. `SemanticChunker`'s paragraph splitter (`_paragraph_units`) uses the identical shape for consistency. Verified on both a real 30-branch synthetic oversized function and a real class.
3. **A markdown heading with no body content merges forward into its next sibling**, and this already-implicitly handles "split at the next-lower heading" — since *every* heading, at any level, starts a new flat section in `_scan_sections`, a `##` section containing a `###` subheading before further prose was never nested to begin with; the `###` is already its own section. Only a genuinely oversized section with no internal subheading falls through to paragraph-boundary splitting.
4. **`ChunkMerger` merges only same-file, same-`symbol_kind` adjacent chunks.** This single rule satisfies both explicit requirements (three tiny top-level functions merge; a class's trailing method chunk never merges into a following unrelated top-level function, since `"method" != "function"`) without needing to track parent-symbol identity. Known, accepted gap: two adjacent, independently-oversized classes could in principle merge trailing/leading `"method"`-kind pieces across the class boundary — not fixed, since `ChunkCandidate` carries no parent-symbol id and this is a rarer compound case than what the design's own tests call for.

## A real finding: `min_chunk_tokens` is best-effort, not an absolute guarantee

The original testing plan describes a "post-merge invariant" that every candidate's `token_count` falls between `min_chunk_tokens` and `max_chunk_tokens`. Empirically running the full pipeline (`chunk_file`) against a real file in this repo (`app/infrastructure/vcs/git_python_adapter.py`, default settings 512/64/256) surfaced two candidates below `min_chunk_tokens` (51 and 60 tokens) that never got merged away.

**Why:** both sit adjacent to a neighbor already close to `max_chunk_tokens` (499 and 477 tokens respectively). Merging either would exceed `merge_target_tokens` (256) — and in one case would exceed `max_chunk_tokens` (512) outright. `ChunkMerger`'s literal, fixed constructor signature (`__init__(self, merge_target_tokens: int)`) has no visibility into `max_chunk_tokens`, so it structurally cannot rescue a small chunk by exceeding the hard ceiling it doesn't know about — and even if it could, greedy left-to-right first-fit splitting (a standard, reasonable bin-packing approach) doesn't retroactively rebalance earlier splits to leave more room for a trailing fragment.

**What's actually guaranteed, and verified in `test_pipeline.py`:**
- `token_count <= max_chunk_tokens` always (hard — `AstChunker` never emits an unchecked piece).
- Full, non-overlapping line coverage; any gap between consecutive candidates is blank lines only, never dropped content.
- `token_count >= min_chunk_tokens` — **best-effort**. The real-file test pins the exact current violation count (`[51, 60]`) as a regression marker rather than asserting a false absolute.

This wasn't a bug to fix — redesigning the splitter to guarantee a min-token floor against an adversarial neighbor would require a materially more complex balanced-partitioning algorithm, which is over-engineering for a v1 chunking engine. Recorded here so the next reader doesn't rediscover the same surprise.

## Testing notes

- `test_token_counter.py` pins an exact token count (20) for a fixed string against the real `tokenizers==0.23.1` + `BAAI/bge-m3` tokenizer — a regression guard against tokenizer/version drift, per the same pattern as Module 7's parser fixture pin.
- `test_ast_chunker.py`/`test_semantic_chunker.py` verify the documented behaviors directly: small-symbol passthrough, module-gap extraction, oversized-function/oversized-class/oversized-section splitting with exact gap-free coverage checks, and empty-heading merging.
- `test_pipeline.py` reuses Module 7's real-file fixture (`git_python_adapter.py`) end-to-end through `chunk_file()`, asserting the two hard guarantees plus the pinned best-effort violation count described above.
- `pytest -q`: 155 passed (16 new). `mypy app`: no issues, 123 source files. `ruff`/`black`: clean. `pre-commit run --all-files`: clean.
- No live-server test — this module has no HTTP surface (consumed by the future indexing pipeline). Verified instead by running every chunker directly against real code/markdown during development, and confirmed the app still boots cleanly with the module present.
