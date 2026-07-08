from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from app.api.deps import require_current_user, require_workspace_access
from app.api.middleware.rate_limit import rate_limit_by_user
from app.api.schemas.common import Envelope
from app.api.schemas.conversation import (
    ConversationResponse,
    CreateConversationRequest,
    MessageResponse,
    SendMessageRequest,
)
from app.api.streaming.events import CitationEvent, DoneEvent, ErrorEvent, SSEEventName, TokenEvent
from app.api.streaming.sse import sse_response
from app.application.use_cases.chat.manage_conversation import ManageConversationUseCase
from app.core.config import get_settings
from app.core.di import provide_agent_graph, provide_manage_conversation_use_case
from app.domain.entities.conversation import Conversation
from app.domain.entities.message import Citation, Message, MessageRole
from app.domain.entities.user import User
from app.domain.entities.workspace import Workspace
from app.infrastructure.db.session import db_session_context

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/conversations", tags=["conversations"])


def _to_response(conversation: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=conversation.id,
        workspace_id=conversation.workspace_id,
        user_id=conversation.user_id,
        title=conversation.title,
        summary=conversation.summary,
        turn_count=conversation.turn_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _message_to_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role.value,
        content=message.content,
        citations=[
            CitationEvent(
                chunk_id=c.chunk_id,
                file_path=c.file_path,
                start_line=c.start_line,
                end_line=c.end_line,
                score=c.score,
            )
            for c in message.citations
        ],
        token_count=message.token_count,
        created_at=message.created_at,
    )


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: CreateConversationRequest,
    workspace: Annotated[Workspace, Depends(require_workspace_access)],
    user: Annotated[User, Depends(require_current_user)],
    use_case: Annotated[ManageConversationUseCase, Depends(provide_manage_conversation_use_case)],
) -> ConversationResponse:
    conversation = await use_case.create_conversation(workspace.id, user.id, body.title)
    return _to_response(conversation)


@router.get("", response_model=Envelope[list[ConversationResponse]])
async def list_conversations(
    workspace: Annotated[Workspace, Depends(require_workspace_access)],
    user: Annotated[User, Depends(require_current_user)],
    use_case: Annotated[ManageConversationUseCase, Depends(provide_manage_conversation_use_case)],
) -> Envelope[list[ConversationResponse]]:
    conversations = await use_case.list_conversations(user.id, workspace.id)
    items = [_to_response(c) for c in conversations]
    return Envelope(data=items, meta={"count": len(items)})


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    workspace: Annotated[Workspace, Depends(require_workspace_access)],
    use_case: Annotated[ManageConversationUseCase, Depends(provide_manage_conversation_use_case)],
) -> ConversationResponse:
    # ConversationNotFoundError propagates to the global domain exception
    # handler (404) — see app/api/middleware/error_handling.py.
    conversation = await use_case.get_conversation(conversation_id, workspace.id)
    return _to_response(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    workspace: Annotated[Workspace, Depends(require_workspace_access)],
    use_case: Annotated[ManageConversationUseCase, Depends(provide_manage_conversation_use_case)],
) -> None:
    await use_case.delete_conversation(conversation_id, workspace.id)


@router.get("/{conversation_id}/messages", response_model=Envelope[list[MessageResponse]])
async def list_messages(
    conversation_id: UUID,
    workspace: Annotated[Workspace, Depends(require_workspace_access)],
    use_case: Annotated[ManageConversationUseCase, Depends(provide_manage_conversation_use_case)],
) -> Envelope[list[MessageResponse]]:
    messages = await use_case.list_messages(conversation_id, workspace.id)
    items = [_message_to_response(m) for m in messages]
    return Envelope(data=items, meta={"count": len(items)})


async def _agent_event_source(
    graph: CompiledStateGraph, initial_state: dict[str, object]
) -> AsyncGenerator[tuple[SSEEventName, BaseModel], None]:
    """Bridges the compiled agent graph's astream() output into the SSE
    event shape sse_response() expects — deliberately owned here (Module
    17), not in Module 16's generic streaming package, per the design's
    own file ownership: the streaming transport is generic, but knowing
    how to translate *this specific graph's* output into token/citation/
    done events is endpoint-specific glue.
    """
    final_state: dict[str, object] = {}
    async for mode, payload in graph.astream(initial_state, stream_mode=["custom", "values"]):
        if mode == "custom" and isinstance(payload, dict) and payload.get("type") == "token":
            yield (SSEEventName.TOKEN, TokenEvent(text=str(payload["text"])))
        elif mode == "values" and isinstance(payload, dict):
            final_state = payload

    citations = final_state.get("citations") or []
    assert isinstance(citations, list)
    for citation in citations:
        assert isinstance(citation, Citation)
        yield (
            SSEEventName.CITATION,
            CitationEvent(
                chunk_id=citation.chunk_id,
                file_path=citation.file_path,
                start_line=citation.start_line,
                end_line=citation.end_line,
                score=citation.score,
            ),
        )

    error = final_state.get("error")
    if error:
        yield (
            SSEEventName.ERROR,
            ErrorEvent(type="agent_error", title="Agent error", detail=str(error)),
        )
    else:
        yield (SSEEventName.DONE, DoneEvent())


@router.post(
    "/{conversation_id}/messages",
    dependencies=[
        Depends(rate_limit_by_user(lambda: get_settings().rate_limit.chat_per_user_per_minute))
    ],
)
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    request: Request,
    workspace: Annotated[Workspace, Depends(require_workspace_access)],
    user: Annotated[User, Depends(require_current_user)],
    use_case: Annotated[ManageConversationUseCase, Depends(provide_manage_conversation_use_case)],
) -> StreamingResponse:
    # Everything up to here runs on the normal request-scoped session and
    # completes before this handler returns, so it's safe: validates the
    # conversation exists and belongs to this workspace (404 via the
    # global handler otherwise) and persists the user's own message.
    await use_case.get_conversation(conversation_id, workspace.id)
    await use_case.append_message(conversation_id, MessageRole.USER, body.content)

    settings = get_settings()
    summary, history = await use_case.get_context_window(
        conversation_id, max_turns=settings.conversation.context_window_turns
    )

    initial_state: dict[str, object] = {
        "conversation_id": conversation_id,
        "workspace_id": workspace.id,
        "user_id": user.id,
        "query": body.content,
        "embedding_version": settings.embedding.model_id,
        "conversation_summary": summary,
        "messages": history,
        "retrieval_attempts": 0,
        "tool_calls": [],
    }

    async def event_source() -> AsyncGenerator[tuple[SSEEventName, BaseModel], None]:
        # A session scoped to this generator's own lifetime, not the
        # request's — verified directly that FastAPI's
        # Depends(get_db_session) commits and closes its session *before*
        # a StreamingResponse body generator starts running, which would
        # silently lose the assistant's message that finalize_node
        # persists via the agent graph built from this session. See
        # db_session_context()'s docstring and docs/modules/rest_api.md.
        async with db_session_context() as stream_session:
            agent_graph = provide_agent_graph(stream_session)
            async for event in _agent_event_source(agent_graph, initial_state):
                yield event

    return await sse_response(request, event_source())
