from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingResult:
    dense: list[float]  # always EMBEDDING_DIM (1024) elements — see core/constants.py
    sparse: dict[int, float]  # token_id -> lexical weight
    model_id: str
