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
    # "reranked" is reserved for Module 12 (Reranker), which doesn't exist
    # yet — RetrievalService.retrieve() currently returns "fused" results.
    source: Literal["dense", "sparse", "fused", "reranked"]
    text: str | None = None
