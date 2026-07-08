from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.entities.message import Citation, Message, MessageRole
from app.domain.entities.user import User
from app.domain.entities.workspace import Workspace
from app.domain.exceptions import ConversationNotFoundError
from app.infrastructure.db.repositories.sqlalchemy_conversation_repository import (
    SqlAlchemyConversationRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_message_repository import (
    SqlAlchemyMessageRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_workspace_repository import (
    SqlAlchemyWorkspaceRepository,
)

pytestmark = pytest.mark.integration

_PLACEHOLDER_TS = datetime.now(UTC)  # overwritten by server_default on insert


async def _seed_user(session) -> User:  # type: ignore[no-untyped-def]
    return await SqlAlchemyUserRepository(session).add(
        User(
            id=uuid4(),
            email=f"{uuid4()}@example.com",
            hashed_password="hashed",
            full_name=None,
            is_active=True,
            is_verified=False,
            created_at=_PLACEHOLDER_TS,
            updated_at=_PLACEHOLDER_TS,
        )
    )


async def _seed_workspace(session, owner_id):  # type: ignore[no-untyped-def]
    return await SqlAlchemyWorkspaceRepository(session).add(
        Workspace(
            id=uuid4(),
            owner_id=owner_id,
            name="Test Workspace",
            slug=f"test-{uuid4().hex[:8]}",
            description=None,
            created_at=_PLACEHOLDER_TS,
            updated_at=_PLACEHOLDER_TS,
        )
    )


def _conversation(workspace_id, user_id, **overrides):  # type: ignore[no-untyped-def]
    from app.domain.entities.conversation import Conversation

    defaults: dict[str, object] = dict(
        id=uuid4(),
        workspace_id=workspace_id,
        user_id=user_id,
        title="Test conversation",
        summary=None,
        turn_count=0,
        is_deleted=False,
        created_at=_PLACEHOLDER_TS,
        updated_at=_PLACEHOLDER_TS,
    )
    defaults.update(overrides)
    return Conversation(**defaults)  # type: ignore[arg-type]


async def test_add_and_get_by_id_round_trips_a_conversation(db_session) -> None:  # type: ignore[no-untyped-def]
    user = await _seed_user(db_session)
    workspace = await _seed_workspace(db_session, user.id)
    repo = SqlAlchemyConversationRepository(db_session)

    added = await repo.add(_conversation(workspace.id, user.id, title="hello"))
    fetched = await repo.get_by_id(added.id)

    assert fetched is not None
    assert fetched.id == added.id
    assert fetched.title == "hello"
    assert fetched.turn_count == 0
    assert fetched.is_deleted is False


async def test_get_by_id_returns_none_for_unknown_id(db_session) -> None:  # type: ignore[no-untyped-def]
    repo = SqlAlchemyConversationRepository(db_session)
    assert await repo.get_by_id(uuid4()) is None


async def test_increment_turn_count_persists_and_returns_new_value(db_session) -> None:  # type: ignore[no-untyped-def]
    user = await _seed_user(db_session)
    workspace = await _seed_workspace(db_session, user.id)
    repo = SqlAlchemyConversationRepository(db_session)
    conversation = await repo.add(_conversation(workspace.id, user.id))

    first = await repo.increment_turn_count(conversation.id)
    second = await repo.increment_turn_count(conversation.id)

    assert (first, second) == (1, 2)
    fetched = await repo.get_by_id(conversation.id)
    assert fetched is not None
    assert fetched.turn_count == 2


async def test_increment_turn_count_raises_conversation_not_found_for_unknown_id(
    db_session,  # type: ignore[no-untyped-def]
) -> None:
    repo = SqlAlchemyConversationRepository(db_session)
    with pytest.raises(ConversationNotFoundError):
        await repo.increment_turn_count(uuid4())


async def test_update_summary_persists_the_new_summary(db_session) -> None:  # type: ignore[no-untyped-def]
    user = await _seed_user(db_session)
    workspace = await _seed_workspace(db_session, user.id)
    repo = SqlAlchemyConversationRepository(db_session)
    conversation = await repo.add(_conversation(workspace.id, user.id))

    await repo.update_summary(conversation.id, "the user asked about auth")

    fetched = await repo.get_by_id(conversation.id)
    assert fetched is not None
    assert fetched.summary == "the user asked about auth"


async def test_soft_delete_sets_is_deleted_but_get_by_id_still_returns_the_row(
    db_session,  # type: ignore[no-untyped-def]
) -> None:
    user = await _seed_user(db_session)
    workspace = await _seed_workspace(db_session, user.id)
    repo = SqlAlchemyConversationRepository(db_session)
    conversation = await repo.add(_conversation(workspace.id, user.id))

    await repo.soft_delete(conversation.id)

    fetched = await repo.get_by_id(conversation.id)
    assert fetched is not None
    assert fetched.is_deleted is True


async def test_list_for_user_excludes_soft_deleted_and_other_users_conversations(
    db_session,  # type: ignore[no-untyped-def]
) -> None:
    user = await _seed_user(db_session)
    other_user = await _seed_user(db_session)
    workspace = await _seed_workspace(db_session, user.id)
    repo = SqlAlchemyConversationRepository(db_session)

    kept = await repo.add(_conversation(workspace.id, user.id, title="kept"))
    to_delete = await repo.add(_conversation(workspace.id, user.id, title="deleted"))
    await repo.soft_delete(to_delete.id)
    await repo.add(_conversation(workspace.id, other_user.id, title="not this user"))

    results = await repo.list_for_user(user.id, None, limit=10, offset=0)

    assert [c.id for c in results] == [kept.id]


async def test_list_for_user_filters_by_workspace_when_given(db_session) -> None:  # type: ignore[no-untyped-def]
    user = await _seed_user(db_session)
    workspace_a = await _seed_workspace(db_session, user.id)
    workspace_b = await _seed_workspace(db_session, user.id)
    repo = SqlAlchemyConversationRepository(db_session)

    in_a = await repo.add(_conversation(workspace_a.id, user.id))
    await repo.add(_conversation(workspace_b.id, user.id))

    results = await repo.list_for_user(user.id, workspace_a.id, limit=10, offset=0)

    assert [c.id for c in results] == [in_a.id]


async def test_message_append_and_list_recent_round_trips_citations_in_chronological_order(
    db_session,  # type: ignore[no-untyped-def]
) -> None:
    user = await _seed_user(db_session)
    workspace = await _seed_workspace(db_session, user.id)
    conversation_repo = SqlAlchemyConversationRepository(db_session)
    message_repo = SqlAlchemyMessageRepository(db_session)
    conversation = await conversation_repo.add(_conversation(workspace.id, user.id))

    citation = Citation(
        chunk_id=uuid4(), file_path="app/foo.py", start_line=1, end_line=5, score=0.9
    )
    first = await message_repo.append(
        Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="what does foo do?",
            citations=[],
            token_count=5,
        )
    )
    second = await message_repo.append(
        Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="it does x",
            citations=[citation],
            token_count=3,
        )
    )

    recent = await message_repo.list_recent(conversation.id, limit=10)

    assert [m.id for m in recent] == [first.id, second.id]  # chronological, not insertion-reversed
    assert recent[1].citations == [citation]  # jsonb round-trip fidelity
    assert recent[0].citations == []


async def test_message_list_recent_respects_limit_keeping_the_most_recent(
    db_session,  # type: ignore[no-untyped-def]
) -> None:
    user = await _seed_user(db_session)
    workspace = await _seed_workspace(db_session, user.id)
    conversation_repo = SqlAlchemyConversationRepository(db_session)
    message_repo = SqlAlchemyMessageRepository(db_session)
    conversation = await conversation_repo.add(_conversation(workspace.id, user.id))

    messages = [
        await message_repo.append(
            Message(
                id=uuid4(),
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content=f"message {i}",
                citations=[],
                token_count=1,
            )
        )
        for i in range(5)
    ]

    recent = await message_repo.list_recent(conversation.id, limit=2)

    assert [m.id for m in recent] == [messages[3].id, messages[4].id]
