from uuid import uuid4

from qdrant_client import models

from app.infrastructure.vectorstore.filters import build_tenant_filter


def test_always_includes_workspace_id_condition() -> None:
    workspace_id = uuid4()

    result = build_tenant_filter(workspace_id)

    assert result.must == [
        models.FieldCondition(key="workspace_id", match=models.MatchValue(value=str(workspace_id)))
    ]


def test_adds_repository_id_condition_when_given() -> None:
    workspace_id, repository_id = uuid4(), uuid4()

    result = build_tenant_filter(workspace_id, repository_id=repository_id)

    assert result.must is not None
    assert len(result.must) == 2
    assert (
        models.FieldCondition(
            key="repository_id", match=models.MatchValue(value=str(repository_id))
        )
        in result.must
    )


def test_adds_file_id_condition_when_given() -> None:
    workspace_id, file_id = uuid4(), uuid4()

    result = build_tenant_filter(workspace_id, file_id=file_id)

    assert result.must is not None
    assert models.FieldCondition(key="file_id", match=models.MatchValue(value=str(file_id))) in (
        result.must
    )


def test_adds_extra_filters() -> None:
    workspace_id = uuid4()

    result = build_tenant_filter(workspace_id, extra={"language": "python"})

    assert result.must is not None
    assert (
        models.FieldCondition(key="language", match=models.MatchValue(value="python"))
        in result.must
    )


def test_every_combination_includes_workspace_id() -> None:
    workspace_id = uuid4()
    combos = [
        build_tenant_filter(workspace_id),
        build_tenant_filter(workspace_id, repository_id=uuid4()),
        build_tenant_filter(workspace_id, file_id=uuid4()),
        build_tenant_filter(workspace_id, repository_id=uuid4(), file_id=uuid4()),
        build_tenant_filter(workspace_id, extra={"language": "python", "symbol_kind": "function"}),
    ]

    workspace_condition = models.FieldCondition(
        key="workspace_id", match=models.MatchValue(value=str(workspace_id))
    )
    for filter_ in combos:
        assert filter_.must is not None
        assert workspace_condition in filter_.must
