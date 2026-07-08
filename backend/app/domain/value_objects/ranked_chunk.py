from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class RankedChunk:
    chunk_id: UUID
    file_path: str
    start_line: int
    end_line: int
    symbol_name: str | None
    score: float
    # "fused" = RetrievalService.retrieve_without_rerank() results (no
    # reranker call); "reranked" = RetrievalService.retrieve() results
    # (Module 12's CrossEncoderReranker has scored and reordered these).
    source: Literal["dense", "sparse", "fused", "reranked"]
    text: str | None = None
