from app.infrastructure.chunking.ast_chunker import AstChunker
from app.infrastructure.chunking.chunk_merger import ChunkMerger
from app.infrastructure.chunking.models import ChunkCandidate
from app.infrastructure.parsing.models import ChunkMetadataCandidate, ParsedFile


def chunk_file(
    parsed: ParsedFile,
    metadata: list[ChunkMetadataCandidate],
    file_path: str,
    *,
    max_chunk_tokens: int,
    min_chunk_tokens: int,
    merge_target_tokens: int,
) -> list[ChunkCandidate]:
    """The chunking engine's public entry point for CODE files: AstChunker
    over the file's symbols, then ChunkMerger to bring undersized
    fragments up to a useful retrieval size.

    Markdown files never go through Module 7's tree-sitter parsing in the
    first place (there's no markdown grammar registered), so they have no
    `ParsedFile`/`ChunkMetadataCandidate` to hand this function — the
    future indexing pipeline chunks them directly via
    `SemanticChunker(...).chunk(markdown_text, file_path)` instead of
    going through here.
    """
    symbols = [m.symbol for m in metadata]
    candidates = AstChunker(max_chunk_tokens, min_chunk_tokens).chunk(parsed, symbols, file_path)
    return ChunkMerger(merge_target_tokens).merge(candidates)
