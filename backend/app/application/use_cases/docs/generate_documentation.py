from enum import Enum
from uuid import UUID

from app.application.services.retrieval_service import RetrievalService
from app.domain.ports.llm_port import LLMPort
from app.domain.value_objects.retrieval_query import RetrievalFilters, RetrievalQuery
from app.infrastructure.llm.prompt_renderer import PromptRenderer


class DocGenerationScope(str, Enum):
    FILE = "file"
    MODULE = "module"
    REPOSITORY = "repository"


# Retrieval here isn't answering a user's question — there's no natural
# query text — so each scope gets a fixed, generic prompt whose sparse
# (lexical) component still surfaces path-relevant chunks reasonably
# well, while repository_id/path_prefix (not the query text) do the real
# scoping work.
_SCOPE_QUERY_TEXT: dict[DocGenerationScope, str] = {
    DocGenerationScope.FILE: "code and behavior implemented in this file",
    DocGenerationScope.MODULE: "code and behavior implemented in this module",
    DocGenerationScope.REPOSITORY: "overview of the repository's architecture and main components",
}


class GenerateDocumentationUseCase:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        llm_port: LLMPort,
        prompt_renderer: PromptRenderer,
        embedding_version: str,
        max_tokens: int = 4096,
        chunk_count: int = 20,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._llm_port = llm_port
        self._prompt_renderer = prompt_renderer
        self._embedding_version = embedding_version
        self._max_tokens = max_tokens
        self._chunk_count = chunk_count

    async def execute(
        self,
        workspace_id: UUID,
        repository_id: UUID,
        scope: DocGenerationScope,
        path: str | None,
    ) -> str:
        query = RetrievalQuery(
            workspace_id=workspace_id,
            query_text=_SCOPE_QUERY_TEXT[scope],
            embedding_version=self._embedding_version,
            repository_id=repository_id,
            filters=RetrievalFilters(
                path_prefix=path if scope is not DocGenerationScope.REPOSITORY else None
            ),
            n=self._chunk_count,
        )
        chunks = await self._retrieval_service.retrieve(query)

        chunk_dicts = [
            {
                "file_path": chunk.file_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "text": chunk.text or "",
            }
            for chunk in chunks
        ]
        prompt = self._prompt_renderer.render(
            "docs_generation.jinja", scope=scope.value, path=path, chunks=chunk_dicts
        )
        result = await self._llm_port.complete(prompt, max_tokens=self._max_tokens, temperature=0.2)
        return result.text
