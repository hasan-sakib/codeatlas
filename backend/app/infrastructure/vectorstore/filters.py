from collections.abc import Mapping
from typing import Any
from uuid import UUID

from qdrant_client import models


def build_tenant_filter(
    workspace_id: UUID,
    *,
    repository_id: UUID | None = None,
    file_id: UUID | None = None,
    extra: Mapping[str, Any] | None = None,
) -> models.Filter:
    """The one and only place a `Filter` touching `workspace_id` is
    constructed — every query-issuing method on `QdrantVectorStore` routes
    through here, so the tenant-isolation guarantee is a code-structure
    guarantee (single call site), not a convention callers must remember.
    """
    must: list[models.Condition] = [
        models.FieldCondition(key="workspace_id", match=models.MatchValue(value=str(workspace_id)))
    ]
    if repository_id is not None:
        must.append(
            models.FieldCondition(
                key="repository_id", match=models.MatchValue(value=str(repository_id))
            )
        )
    if file_id is not None:
        must.append(
            models.FieldCondition(key="file_id", match=models.MatchValue(value=str(file_id)))
        )
    if extra:
        for key, value in extra.items():
            must.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
    return models.Filter(must=must)
