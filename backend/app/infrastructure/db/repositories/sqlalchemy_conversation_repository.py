from uuid import UUID

from sqlalchemy import select, update

from app.domain.entities.conversation import Conversation
from app.domain.exceptions import ConversationNotFoundError
from app.domain.ports.conversation_repository import ConversationRepository
from app.infrastructure.db.models.conversation import ConversationModel
from app.infrastructure.db.repositories.base_repository import SqlAlchemyRepository


def _to_entity(model: ConversationModel) -> Conversation:
    return Conversation(
        id=model.id,
        workspace_id=model.workspace_id,
        user_id=model.user_id,
        title=model.title,
        summary=model.summary,
        turn_count=model.turn_count,
        is_deleted=model.is_deleted,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyConversationRepository(SqlAlchemyRepository, ConversationRepository):
    async def add(self, conversation: Conversation) -> Conversation:
        model = ConversationModel(
            id=conversation.id,
            workspace_id=conversation.workspace_id,
            user_id=conversation.user_id,
            title=conversation.title,
            summary=conversation.summary,
            turn_count=conversation.turn_count,
            is_deleted=conversation.is_deleted,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _to_entity(model)

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        model = await self.session.get(ConversationModel, conversation_id)
        return _to_entity(model) if model else None

    async def list_for_user(
        self, user_id: UUID, workspace_id: UUID | None, limit: int, offset: int
    ) -> list[Conversation]:
        stmt = select(ConversationModel).where(
            ConversationModel.user_id == user_id,
            ConversationModel.is_deleted.is_(False),
        )
        if workspace_id is not None:
            stmt = stmt.where(ConversationModel.workspace_id == workspace_id)
        stmt = stmt.order_by(ConversationModel.updated_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return [_to_entity(m) for m in result.scalars().all()]

    async def update_summary(self, conversation_id: UUID, summary: str) -> None:
        await self.session.execute(
            update(ConversationModel)
            .where(ConversationModel.id == conversation_id)
            .values(summary=summary)
        )

    async def increment_turn_count(self, conversation_id: UUID) -> int:
        model = await self.session.get(ConversationModel, conversation_id)
        if model is None:
            raise ConversationNotFoundError(conversation_id)
        model.turn_count += 1
        await self.session.flush()
        return model.turn_count

    async def soft_delete(self, conversation_id: UUID) -> None:
        await self.session.execute(
            update(ConversationModel)
            .where(ConversationModel.id == conversation_id)
            .values(is_deleted=True)
        )
