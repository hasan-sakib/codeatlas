from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ports.chunk_repository import ChunkRepository
from app.domain.ports.conversation_repository import ConversationRepository
from app.domain.ports.file_repository import FileRepository
from app.domain.ports.indexing_job_repository import IndexingJobRepository
from app.domain.ports.message_repository import MessageRepository
from app.domain.ports.refresh_token_repository import RefreshTokenRepository
from app.domain.ports.repository_repository import RepositoryRepository
from app.domain.ports.token_blacklist import TokenBlacklistPort
from app.domain.ports.user_repository import UserRepository
from app.domain.ports.workspace_repository import WorkspaceRepository
from app.infrastructure.cache.redis_client import get_redis_client
from app.infrastructure.cache.redis_token_blacklist import RedisTokenBlacklistAdapter
from app.infrastructure.db.repositories.sqlalchemy_chunk_repository import (
    SqlAlchemyChunkRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_conversation_repository import (
    SqlAlchemyConversationRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_file_repository import (
    SqlAlchemyFileRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_indexing_job_repository import (
    SqlAlchemyIndexingJobRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_message_repository import (
    SqlAlchemyMessageRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_refresh_token_repository import (
    SqlAlchemyRefreshTokenRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_repository_repository import (
    SqlAlchemyRepositoryRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)
from app.infrastructure.db.repositories.sqlalchemy_workspace_repository import (
    SqlAlchemyWorkspaceRepository,
)
from app.infrastructure.db.session import get_db_session

# The single FastAPI-dependency-annotated session type every repository
# provider below builds on — one session per request (see session.py).
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def provide_user_repository(session: DbSession) -> UserRepository:
    return SqlAlchemyUserRepository(session)


def provide_refresh_token_repository(session: DbSession) -> RefreshTokenRepository:
    return SqlAlchemyRefreshTokenRepository(session)


def provide_workspace_repository(session: DbSession) -> WorkspaceRepository:
    return SqlAlchemyWorkspaceRepository(session)


def provide_repository_repository(session: DbSession) -> RepositoryRepository:
    return SqlAlchemyRepositoryRepository(session)


def provide_indexing_job_repository(session: DbSession) -> IndexingJobRepository:
    return SqlAlchemyIndexingJobRepository(session)


def provide_file_repository(session: DbSession) -> FileRepository:
    return SqlAlchemyFileRepository(session)


def provide_chunk_repository(session: DbSession) -> ChunkRepository:
    return SqlAlchemyChunkRepository(session)


def provide_conversation_repository(session: DbSession) -> ConversationRepository:
    return SqlAlchemyConversationRepository(session)


def provide_message_repository(session: DbSession) -> MessageRepository:
    return SqlAlchemyMessageRepository(session)


def provide_token_blacklist() -> TokenBlacklistPort:
    return RedisTokenBlacklistAdapter(get_redis_client())
