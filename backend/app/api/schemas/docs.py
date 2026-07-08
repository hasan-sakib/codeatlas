from pydantic import BaseModel, model_validator

from app.application.use_cases.docs.generate_documentation import DocGenerationScope


class GenerateDocsRequest(BaseModel):
    scope: DocGenerationScope
    path: str | None = None

    @model_validator(mode="after")
    def _path_required_unless_repository_scope(self) -> "GenerateDocsRequest":
        if self.scope is not DocGenerationScope.REPOSITORY and not self.path:
            raise ValueError(f"path is required for scope={self.scope.value}")
        return self


class GenerateDocsResponse(BaseModel):
    scope: DocGenerationScope
    path: str | None
    markdown: str
