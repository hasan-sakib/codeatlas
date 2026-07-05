from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.domain.entities.message import Citation, Message
from app.domain.ports.message_repository import MessageRepository
from app.infrastructure.db.models.message import MessageModel
from app.infrastructure.db.repositories.base_repository import SqlAlchemyRepository


def _citation_to_dict(citation: Citation) -> dict[str, Any]:
    return {
        "chunk_id": str(citation.chunk_id),
        "file_path": citation.file_path,
        "start_line": citation.start_line,
        "end_line": citation.end_line,
        "score": citation.score,
    }


def _citation_from_dict(data: dict[str, Any]) -> Citation:
    return Citation(
        chunk_id=UUID(data["chunk_id"]),
        file_path=data["file_path"],
        start_line=data["start_line"],
        end_line=data["end_line"],
        score=data["score"],
    )


def _to_entity(model: MessageModel) -> Message:
    return Message(
        id=model.id,
        conversation_id=model.conversation_id,
        role=model.role,
        content=model.content,
        citations=[_citation_from_dict(c) for c in (model.citations or [])],
        token_count=model.token_count,
        created_at=model.created_at,
    )


class SqlAlchemyMessageRepository(SqlAlchemyRepository, MessageRepository):
    async def append(self, message: Message) -> Message:
        model = MessageModel(
            id=message.id,
            conversation_id=message.conversation_id,
            role=message.role,
            content=message.content,
            citations=[_citation_to_dict(c) for c in message.citations],
            token_count=message.token_count,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _to_entity(model)

    async def list_recent(self, conversation_id: UUID, limit: int) -> list[Message]:
        result = await self.session.execute(
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.desc())
            .limit(limit)
        )
        models = list(result.scalars().all())
        models.reverse()  # chronological order
        return [_to_entity(m) for m in models]
