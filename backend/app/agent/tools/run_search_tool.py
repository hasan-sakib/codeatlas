from typing import ClassVar
from uuid import UUID

from app.application.services.retrieval_service import RetrievalService
from app.domain.value_objects.retrieval_query import RetrievalQuery


class RunSearchTool:
    """Ad hoc secondary search with a fresh query — for widening beyond
    whatever the main retrieve_context/rerank pass already surfaced,
    e.g. "search again with different words" rather than re-running the
    same query with wider k1/k2 (that's assess_sufficiency's job)."""

    name: ClassVar[str] = "run_search"

    def __init__(self, retrieval_service: RetrievalService) -> None:
        self._retrieval_service = retrieval_service

    async def __call__(self, query_text: str, workspace_id: UUID, embedding_version: str) -> str:
        results = await self._retrieval_service.retrieve(
            RetrievalQuery(
                workspace_id=workspace_id,
                query_text=query_text,
                embedding_version=embedding_version,
            )
        )
        if not results:
            return f"No results found for: {query_text}"

        lines = [
            f"{r.file_path}:{r.start_line}-{r.end_line} (score={r.score:.3f})" for r in results
        ]
        return "\n".join(lines)
