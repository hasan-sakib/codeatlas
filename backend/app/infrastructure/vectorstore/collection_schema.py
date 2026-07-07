from qdrant_client import AsyncQdrantClient, models

from app.core.constants import EMBEDDING_DIM, QDRANT_DENSE_VECTOR_NAME, QDRANT_SPARSE_VECTOR_NAME

# Eagerly indexed for efficient filtering — every one of these appears in
# at least one call site's mandatory or optional filter.
_PAYLOAD_INDEXES: dict[str, models.PayloadSchemaType] = {
    "workspace_id": models.PayloadSchemaType.KEYWORD,
    "repository_id": models.PayloadSchemaType.KEYWORD,
    "file_id": models.PayloadSchemaType.KEYWORD,
    "language": models.PayloadSchemaType.KEYWORD,
    "symbol_kind": models.PayloadSchemaType.KEYWORD,
    "embedding_version": models.PayloadSchemaType.KEYWORD,
    "is_active": models.PayloadSchemaType.BOOL,
}


def collection_name_for_version(prefix: str, version: int) -> str:
    return f"{prefix}_v{version}"


def alias_name(prefix: str) -> str:
    return f"{prefix}_active"


def build_vectors_config(embedding_dim: int = EMBEDDING_DIM) -> dict[str, models.VectorParams]:
    return {
        QDRANT_DENSE_VECTOR_NAME: models.VectorParams(
            size=embedding_dim, distance=models.Distance.COSINE
        )
    }


def build_sparse_vectors_config() -> dict[str, models.SparseVectorParams]:
    return {QDRANT_SPARSE_VECTOR_NAME: models.SparseVectorParams()}


async def create_versioned_collection(
    client: AsyncQdrantClient, *, prefix: str, version: int, embedding_dim: int = EMBEDDING_DIM
) -> str:
    collection_name = collection_name_for_version(prefix, version)
    await client.create_collection(
        collection_name=collection_name,
        vectors_config=build_vectors_config(embedding_dim),
        sparse_vectors_config=build_sparse_vectors_config(),
    )
    await ensure_payload_indexes(client, collection_name)
    return collection_name


async def ensure_payload_indexes(client: AsyncQdrantClient, collection_name: str) -> None:
    for field_name, schema in _PAYLOAD_INDEXES.items():
        await client.create_payload_index(
            collection_name=collection_name, field_name=field_name, field_schema=schema
        )


async def point_alias_to(client: AsyncQdrantClient, alias: str, collection_name: str) -> None:
    """A single atomic operation — never two separate calls — so the
    alias is never observably missing mid-cutover. Verified directly:
    Qdrant treats deleting a not-yet-existing alias as a no-op within the
    same batch, so this one implementation covers both first-time
    bootstrap and a later version cutover.
    """
    await client.update_collection_aliases(
        change_aliases_operations=[
            models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias)),
            models.CreateAliasOperation(
                create_alias=models.CreateAlias(collection_name=collection_name, alias_name=alias)
            ),
        ]
    )


async def list_collection_versions(client: AsyncQdrantClient, prefix: str) -> list[str]:
    version_prefix = f"{prefix}_v"
    collections = await client.get_collections()
    return sorted(c.name for c in collections.collections if c.name.startswith(version_prefix))
