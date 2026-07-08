from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import require_repository_access
from app.api.schemas.docs import GenerateDocsRequest, GenerateDocsResponse
from app.application.use_cases.docs.generate_documentation import GenerateDocumentationUseCase
from app.core.di import provide_generate_documentation_use_case
from app.domain.entities.repository import Repository

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/repositories/{repository_id}/docs",
    tags=["docs"],
)


@router.post("/generate", response_model=GenerateDocsResponse)
async def generate_docs(
    body: GenerateDocsRequest,
    repository: Annotated[Repository, Depends(require_repository_access)],
    use_case: Annotated[
        GenerateDocumentationUseCase, Depends(provide_generate_documentation_use_case)
    ],
) -> GenerateDocsResponse:
    markdown = await use_case.execute(
        workspace_id=repository.workspace_id,
        repository_id=repository.id,
        scope=body.scope,
        path=body.path,
    )
    return GenerateDocsResponse(scope=body.scope, path=body.path, markdown=markdown)
