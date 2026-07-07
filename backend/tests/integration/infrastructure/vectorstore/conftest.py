import pytest
from testcontainers.qdrant import QdrantContainer


@pytest.fixture(scope="module")
def qdrant_container():
    # Pinned to match the installed qdrant-client version (1.18.x) —
    # testcontainers' own default image (v1.13.5) throws a client/server
    # compatibility warning against it, verified directly.
    with QdrantContainer(image="qdrant/qdrant:v1.18.2") as container:
        yield container
