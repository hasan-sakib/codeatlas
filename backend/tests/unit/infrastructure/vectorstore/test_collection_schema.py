from unittest.mock import AsyncMock

from qdrant_client import models

from app.core.constants import EMBEDDING_DIM, QDRANT_DENSE_VECTOR_NAME, QDRANT_SPARSE_VECTOR_NAME
from app.infrastructure.vectorstore.collection_schema import (
    alias_name,
    build_sparse_vectors_config,
    build_vectors_config,
    collection_name_for_version,
    create_versioned_collection,
    ensure_payload_indexes,
    point_alias_to,
)


def test_build_vectors_config_matches_embedding_dim_and_cosine() -> None:
    config = build_vectors_config()

    dense = config[QDRANT_DENSE_VECTOR_NAME]
    assert dense.size == EMBEDDING_DIM
    assert dense.distance == models.Distance.COSINE


def test_build_sparse_vectors_config_has_sparse_entry() -> None:
    config = build_sparse_vectors_config()

    assert QDRANT_SPARSE_VECTOR_NAME in config


def test_collection_name_for_version_and_alias_name() -> None:
    assert collection_name_for_version("code_chunks", 1) == "code_chunks_v1"
    assert alias_name("code_chunks") == "code_chunks_active"


async def test_create_versioned_collection_creates_and_indexes() -> None:
    client = AsyncMock()

    name = await create_versioned_collection(
        client, prefix="code_chunks", version=2, embedding_dim=8
    )

    assert name == "code_chunks_v2"
    client.create_collection.assert_awaited_once()
    kwargs = client.create_collection.call_args.kwargs
    assert kwargs["collection_name"] == "code_chunks_v2"
    assert kwargs["vectors_config"][QDRANT_DENSE_VECTOR_NAME].size == 8
    assert client.create_payload_index.await_count == len(
        {
            "workspace_id",
            "repository_id",
            "file_id",
            "language",
            "symbol_kind",
            "embedding_version",
            "is_active",
        }
    )


async def test_ensure_payload_indexes_covers_every_expected_field() -> None:
    client = AsyncMock()

    await ensure_payload_indexes(client, "some_collection")

    indexed_fields = {
        call.kwargs["field_name"] for call in client.create_payload_index.await_args_list
    }
    assert indexed_fields == {
        "workspace_id",
        "repository_id",
        "file_id",
        "language",
        "symbol_kind",
        "embedding_version",
        "is_active",
    }


async def test_point_alias_to_issues_a_single_atomic_call() -> None:
    client = AsyncMock()

    await point_alias_to(client, "code_chunks_active", "code_chunks_v2")

    client.update_collection_aliases.assert_awaited_once()
    operations = client.update_collection_aliases.call_args.kwargs["change_aliases_operations"]
    assert len(operations) == 2
    assert isinstance(operations[0], models.DeleteAliasOperation)
    assert operations[0].delete_alias.alias_name == "code_chunks_active"
    assert isinstance(operations[1], models.CreateAliasOperation)
    assert operations[1].create_alias.alias_name == "code_chunks_active"
    assert operations[1].create_alias.collection_name == "code_chunks_v2"
