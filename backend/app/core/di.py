from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.retrieval_service import RetrievalService
from app.core.config import get_settings
from app.domain.ports.chunk_repository import ChunkRepository
from app.domain.ports.conversation_repository import ConversationRepository
from app.domain.ports.embedding_port import EmbeddingPort
from app.domain.ports.file_repository import FileRepository
from app.domain.ports.git_port import GitPort
from app.domain.ports.indexing_job_repository import IndexingJobRepository
from app.domain.ports.indexing_task_dispatcher import IndexingTaskDispatcherPort
from app.domain.ports.message_repository import MessageRepository
from app.domain.ports.refresh_token_repository import RefreshTokenRepository
from app.domain.ports.repository_repository import RepositoryRepository
from app.domain.ports.token_blacklist import TokenBlacklistPort
from app.domain.ports.user_repository import UserRepository
from app.domain.ports.vector_store_port import VectorStorePort
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
from app.infrastructure.embeddings.bge_m3_adapter import BgeM3Adapter
from app.infrastructure.embeddings.embedding_cache import RedisEmbeddingCache
from app.infrastructure.queue.null_indexing_task_dispatcher import NullIndexingTaskDispatcher
from app.infrastructure.vcs.git_python_adapter import GitPythonAdapter
from app.infrastructure.vectorstore.qdrant_vector_store import QdrantVectorStore

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


def provide_git_port() -> GitPort:
    git_settings = get_settings().git
    return GitPythonAdapter(
        clone_timeout_seconds=git_settings.clone_timeout_seconds,
        max_repo_size_mb=git_settings.max_repo_size_mb,
    )


def provide_indexing_task_dispatcher() -> IndexingTaskDispatcherPort:
    return NullIndexingTaskDispatcher()


@lru_cache(maxsize=1)
def provide_embedding_port() -> EmbeddingPort:
    # Cached singleton: BgeM3Adapter lazily loads the (large) model into
    # its own instance state on first use, so a fresh instance per
    # request would reload the model every single time.
    cache = RedisEmbeddingCache(get_redis_client())
    return BgeM3Adapter(cache, get_settings().embedding)


def clear_embedding_port_cache() -> None:
    """Test-only helper, mirrors clear_settings_cache/clear_redis_client_cache."""
    provide_embedding_port.cache_clear()


@lru_cache(maxsize=1)
def _get_qdrant_client() -> AsyncQdrantClient:
    settings = get_settings().qdrant
    return AsyncQdrantClient(
        url=str(settings.url),
        api_key=settings.api_key.get_secret_value() if settings.api_key else None,
        timeout=int(settings.timeout_seconds),
    )


@lru_cache(maxsize=1)
def provide_vector_store() -> VectorStorePort:
    settings = get_settings().qdrant
    return QdrantVectorStore(_get_qdrant_client(), collection_prefix=settings.collection_prefix)


def clear_vector_store_cache() -> None:
    """Test-only helper, mirrors clear_settings_cache/clear_redis_client_cache."""
    provide_vector_store.cache_clear()
    _get_qdrant_client.cache_clear()


def provide_retrieval_service(session: DbSession) -> RetrievalService:
    # Not cached: chunk_repository/file_repository are session-scoped
    # (fresh per request), unlike the process-wide embedding/vector-store
    # singletons this composes.
    return RetrievalService(
        embedding_port=provide_embedding_port(),
        vector_store_port=provide_vector_store(),
        chunk_repository=provide_chunk_repository(session),
        file_repository=provide_file_repository(session),
    )
