import hashlib
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import structlog

from app.application.services.repository_walker import walk_repository
from app.domain.entities.chunk import Chunk, ChunkType, SymbolKind
from app.domain.entities.file import File
from app.domain.entities.indexing_job import IndexingJob, IndexingJobStatus
from app.domain.entities.repository import Repository, RepositoryStatus
from app.domain.ports.chunk_repository import ChunkRepository
from app.domain.ports.embedding_port import EmbeddingPort
from app.domain.ports.file_repository import FileRepository
from app.domain.ports.git_port import GitPort
from app.domain.ports.indexing_job_repository import IndexingJobRepository
from app.domain.ports.repository_repository import RepositoryRepository
from app.domain.ports.vector_store_port import VectorStorePort
from app.domain.value_objects.chunk_upsert_item import ChunkUpsertItem
from app.infrastructure.chunking.models import ChunkCandidate
from app.infrastructure.chunking.pipeline import chunk_file
from app.infrastructure.chunking.semantic_chunker import SemanticChunker
from app.infrastructure.parsing import parsers  # noqa: F401  registers every language parser
from app.infrastructure.parsing.language_detector import detect_language
from app.infrastructure.parsing.metadata_extractor import MetadataExtractor
from app.infrastructure.parsing.models import ChunkMetadataCandidate
from app.infrastructure.parsing.registry import ParserRegistry, UnsupportedLanguageError

logger = structlog.get_logger(__name__)

_MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown"})

# The Postgres chunks.embedding_version column is a generation counter for
# a future re-embedding-migration workflow (DESIGN.md §15's alias-cutover
# scheme) — that workflow doesn't exist, only one generation has ever
# existed in this codebase's lifetime, so this is a fixed 1, not derived
# from anything. Do not confuse with the *string* embedding_version this
# use case is constructed with, which is the Qdrant payload value
# retrieval's own filters must match (settings.embedding.model_id) — the
# two are unrelated fields on unrelated schemas that happen to share a
# name.
_POSTGRES_EMBEDDING_GENERATION = 1


async def _noop_commit() -> None:
    """Default when the caller has nothing to commit — e.g. unit tests
    with in-memory fakes, which have no real transaction boundary."""


class RunIndexingPipelineUseCase:
    """Clone → walk → (parse+chunk | semantic-chunk) → embed → persist →
    upsert, one file at a time. Per-file processing (rather than global
    parse-all/chunk-all/embed-all/upsert-all phases) trades some
    embedding-batch efficiency for bounded memory and fine-grained,
    file-level progress reporting and failure isolation — a single bad
    file logs a warning and is skipped, never sinking the whole job.

    IndexingJobStatus's PARSING is used as the umbrella status for this
    entire per-file loop, rather than distinct CHUNKING/EMBEDDING/
    UPSERTING phases — those enum members describe global sequential
    phases this per-file design doesn't have. Real granularity comes
    from the job's own files_processed/files_total/chunks_total counters.
    """

    def __init__(
        self,
        repository_repo: RepositoryRepository,
        indexing_job_repo: IndexingJobRepository,
        file_repo: FileRepository,
        chunk_repo: ChunkRepository,
        git_port: GitPort,
        embedding_port: EmbeddingPort,
        vector_store_port: VectorStorePort,
        *,
        max_chunk_tokens: int,
        min_chunk_tokens: int,
        merge_target_tokens: int,
        max_file_size_bytes: int,
        excluded_dir_names: frozenset[str],
        embedding_version: str,
        commit: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._repository_repo = repository_repo
        self._indexing_job_repo = indexing_job_repo
        self._file_repo = file_repo
        self._chunk_repo = chunk_repo
        self._git_port = git_port
        self._embedding_port = embedding_port
        self._vector_store = vector_store_port
        self._max_chunk_tokens = max_chunk_tokens
        self._min_chunk_tokens = min_chunk_tokens
        self._merge_target_tokens = merge_target_tokens
        self._max_file_size_bytes = max_file_size_bytes
        self._excluded_dir_names = excluded_dir_names
        self._embedding_version = embedding_version
        # Committing after every file (not once at the end of the whole
        # job) is what makes a crash mid-job lose only the file in
        # flight instead of every file processed so far — verified
        # directly: a worker restart mid-job previously rolled back an
        # entire 10+ minute run's worth of already-embedded-and-Qdrant-
        # upserted files, since nothing had been committed to Postgres
        # yet, and left those Qdrant points orphaned (no matching
        # Postgres row) since Qdrant's own writes aren't part of this
        # transaction and don't roll back with it.
        self._commit = commit if commit is not None else _noop_commit
        self._metadata_extractor = MetadataExtractor(git_port)

    async def execute(self, job_id: UUID) -> None:
        job = await self._indexing_job_repo.get_by_id(job_id)
        if job is None:
            raise ValueError(f"IndexingJob {job_id} not found")
        repository = await self._repository_repo.get_by_id(job.repository_id)
        if repository is None:
            raise ValueError(f"Repository {job.repository_id} not found")
        if repository.git_url is None:
            raise ValueError(f"Repository {repository.id} has no git_url to clone")

        clone_dir = Path(tempfile.mkdtemp(prefix="codeatlas-index-"))
        try:
            await self._run(job, repository, clone_dir)
        except Exception as exc:
            logger.error("indexing.failed", job_id=str(job_id), error=str(exc))
            # Re-fetch rather than reuse the `job` snapshot from above:
            # per-file commits inside _run() may have already advanced
            # files_processed/chunks_total past what that snapshot
            # holds, and marking failed from the stale copy would
            # overwrite that real progress back to its starting values.
            latest_job = await self._indexing_job_repo.get_by_id(job_id)
            await self._mark_failed(latest_job or job, repository, str(exc))
            raise
        finally:
            shutil.rmtree(clone_dir, ignore_errors=True)

    async def _run(self, job: IndexingJob, repository: Repository, clone_dir: Path) -> None:
        assert repository.git_url is not None  # guarded by execute()

        job = await self._update_job(job, status=IndexingJobStatus.CLONING)
        cloned = await self._git_port.clone(repository.git_url, clone_dir, shallow=True)

        job = await self._update_job(job, status=IndexingJobStatus.WALKING)
        candidates = list(
            walk_repository(
                cloned.local_path,
                max_file_size_bytes=self._max_file_size_bytes,
                excluded_dir_names=self._excluded_dir_names,
            )
        )
        job = await self._update_job(
            job, status=IndexingJobStatus.PARSING, files_total=len(candidates)
        )
        await self._commit()

        files_processed = 0
        chunks_total = 0
        for absolute_path, relative_path in candidates:
            try:
                chunks_total += await self._process_file(
                    repository, cloned.local_path, absolute_path, relative_path
                )
            except Exception as exc:
                logger.warning(
                    "indexing.file_failed",
                    repository_id=str(repository.id),
                    file=relative_path,
                    error=str(exc),
                )
            files_processed += 1
            job = await self._update_job(
                job, files_processed=files_processed, chunks_total=chunks_total
            )
            # Commit per file, not once at the end of the whole job: a
            # crash here must only cost the file in flight, and Qdrant's
            # writes for already-processed files (not transactional with
            # Postgres) must never outlive their Postgres row.
            await self._commit()

        await self._repository_repo.update_status(
            repository.id, RepositoryStatus.READY, last_indexed_commit_sha=cloned.commit_sha
        )
        await self._update_job(
            job, status=IndexingJobStatus.COMPLETED, finished_at=datetime.now(UTC)
        )
        await self._commit()
        logger.info(
            "indexing.completed",
            repository_id=str(repository.id),
            files_processed=files_processed,
            chunks_total=chunks_total,
        )

    async def _process_file(
        self, repository: Repository, repo_root: Path, absolute_path: Path, relative_path: str
    ) -> int:
        """Returns the number of chunks written for this file (0 if
        skipped: unchanged since last index, unsupported, or binary)."""
        content_bytes = absolute_path.read_bytes()
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        existing = await self._file_repo.get_by_repository_and_path(repository.id, relative_path)
        if existing is not None and existing.content_hash == content_hash:
            return 0  # unchanged since the last index — skip re-parsing/re-embedding entirely

        is_markdown = absolute_path.suffix.lower() in _MARKDOWN_EXTENSIONS
        language = detect_language(absolute_path, content_bytes[:256])
        if not is_markdown and language is None:
            return 0  # no parser registered for this file, and it isn't markdown

        try:
            text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return 0  # binary file the extension heuristic didn't catch

        metadata: list[ChunkMetadataCandidate] = []
        if is_markdown:
            candidates = SemanticChunker(self._max_chunk_tokens, self._min_chunk_tokens).chunk(
                text, relative_path
            )
        else:
            assert language is not None
            try:
                parser = ParserRegistry.get_by_language_id(language)
            except UnsupportedLanguageError:
                return 0
            parsed = parser.parse(content_bytes)
            metadata = await self._metadata_extractor.extract(parsed, repo_root, relative_path)
            candidates = chunk_file(
                parsed,
                metadata,
                relative_path,
                max_chunk_tokens=self._max_chunk_tokens,
                min_chunk_tokens=self._min_chunk_tokens,
                merge_target_tokens=self._merge_target_tokens,
            )

        if not candidates:
            return 0

        file_id = existing.id if existing is not None else uuid4()
        chunks = [
            self._to_chunk_entity(candidate, file_id, repository.id, metadata)
            for candidate in candidates
        ]
        # Embed before persisting anything for this file: if this raises,
        # the file's old row (old content_hash, old chunks, old vectors)
        # must be left completely untouched, so a later re-index retries
        # it — persisting the new content_hash first would make a
        # transient embedding failure permanent, since the unchanged-hash
        # skip above would then never re-attempt this file again.
        embeddings = await self._embedding_port.embed_batch([c.content for c in chunks])
        embedded_chunks = [
            replace(
                chunk,
                embedding_model=embedding.model_id,
                embedding_version=_POSTGRES_EMBEDDING_GENERATION,
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]

        await self._file_repo.upsert(
            File(
                id=file_id,
                repository_id=repository.id,
                path=relative_path,
                language=language or "markdown",
                size_bytes=len(content_bytes),
                content_hash=content_hash,
                last_commit_sha=None,
                last_modified_at=datetime.now(UTC),
                is_deleted=False,
                indexed_at=datetime.now(UTC),
            )
        )

        if existing is not None:
            # Re-index of a changed file: stop the old chunks from
            # surfacing in search immediately rather than leaving them
            # live until some future cleanup pass.
            await self._chunk_repo.deactivate_by_file(file_id)

        await self._chunk_repo.add_many(embedded_chunks)

        upsert_items = [
            ChunkUpsertItem(
                chunk_id=chunk.id,
                dense_vector=embedding.dense,
                sparse_vector=embedding.sparse,
                workspace_id=repository.workspace_id,
                repository_id=repository.id,
                file_path=relative_path,
                language=language or "markdown",
                symbol_kind=chunk.symbol_kind.value,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                embedding_version=self._embedding_version,
            )
            for chunk, embedding in zip(embedded_chunks, embeddings, strict=True)
        ]
        await self._vector_store.upsert(upsert_items, workspace_id=repository.workspace_id)

        return len(chunks)

    def _to_chunk_entity(
        self,
        candidate: ChunkCandidate,
        file_id: UUID,
        repository_id: UUID,
        metadata: list[ChunkMetadataCandidate],
    ) -> Chunk:
        # Imports are file-scoped (every symbol in a file shares the same
        # import list — see MetadataExtractor's own docstring), so any
        # entry's imports tuple is representative of the whole file.
        imports = [imp.module for imp in metadata[0].imports] if metadata else []

        # Blame is genuinely per-line-range, and a merged chunk (several
        # small symbols combined by ChunkMerger) may span a range no
        # single original symbol matches exactly — best-effort exact
        # match only; a merged chunk simply carries no blame rather than
        # a misleading partial one.
        blame_match = next(
            (
                m
                for m in metadata
                if m.symbol.start_line == candidate.start_line
                and m.symbol.end_line == candidate.end_line
            ),
            None,
        )
        git_blame = (
            {
                "entries": [
                    {
                        "author": b.author,
                        "commit_sha": b.commit_sha,
                        "committed_at": b.committed_at.isoformat(),
                    }
                    for b in blame_match.blame
                ]
            }
            if blame_match is not None and blame_match.blame
            else None
        )

        return Chunk(
            id=uuid4(),
            file_id=file_id,
            repository_id=repository_id,
            symbol_name=candidate.symbol_name,
            symbol_kind=SymbolKind(candidate.symbol_kind),
            start_line=candidate.start_line,
            end_line=candidate.end_line,
            content=candidate.text,
            content_tokens=candidate.token_count,
            chunk_type=ChunkType.PROSE if candidate.language == "markdown" else ChunkType.CODE,
            imports=imports,
            git_blame=git_blame,
        )

    async def _update_job(self, job: IndexingJob, **overrides: object) -> IndexingJob:
        return await self._indexing_job_repo.update(replace(job, **overrides))  # type: ignore[arg-type]

    async def _mark_failed(
        self, job: IndexingJob, repository: Repository, error_message: str
    ) -> None:
        await self._update_job(
            job,
            status=IndexingJobStatus.FAILED,
            error_message=error_message,
            finished_at=datetime.now(UTC),
        )
        await self._repository_repo.update_status(repository.id, RepositoryStatus.FAILED)
        # execute()'s caller re-raises after this — without an explicit
        # commit here, db_session_context's own exception handler would
        # roll back this exact write, silently discarding the FAILED
        # status it was trying to record.
        await self._commit()
