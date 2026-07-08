from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import require_workspace_access
from app.api.middleware.rate_limit import rate_limit_by_user
from app.api.schemas.common import Envelope
from app.api.schemas.search import SearchRequest, SearchResultItem
from app.application.services.retrieval_service import RetrievalService
from app.core.config import get_settings
from app.core.di import provide_retrieval_service
from app.domain.entities.workspace import Workspace
from app.domain.value_objects.ranked_chunk import RankedChunk
from app.domain.value_objects.retrieval_query import RetrievalFilters, RetrievalQuery

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/search", tags=["search"])


def _to_item(chunk: RankedChunk) -> SearchResultItem:
    return SearchResultItem(
        chunk_id=chunk.chunk_id,
        file_path=chunk.file_path,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        symbol_name=chunk.symbol_name,
        score=chunk.score,
        source=chunk.source,
        text=chunk.text,
    )


@router.post(
    "",
    response_model=Envelope[list[SearchResultItem]],
    dependencies=[
        Depends(rate_limit_by_user(lambda: get_settings().rate_limit.chat_per_user_per_minute))
    ],
)
async def search(
    body: SearchRequest,
    workspace: Annotated[Workspace, Depends(require_workspace_access)],
    retrieval_service: Annotated[RetrievalService, Depends(provide_retrieval_service)],
) -> Envelope[list[SearchResultItem]]:
    # embedding_version is the currently-active model generation
    # (Module 9/10's versioning scheme) — a server-side config value,
    # never a client-supplied request parameter.
    query = RetrievalQuery(
        workspace_id=workspace.id,
        query_text=body.query,
        embedding_version=get_settings().embedding.model_id,
        filters=RetrievalFilters(
            language=body.language,
            path_prefix=body.path_prefix,
            symbol_kind=body.symbol_kind,
        ),
        n=body.limit,
    )
    results = await retrieval_service.retrieve(query)
    items = [_to_item(chunk) for chunk in results]
    return Envelope(data=items, meta={"count": len(items)})
