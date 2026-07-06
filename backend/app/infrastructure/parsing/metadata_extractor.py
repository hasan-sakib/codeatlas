from pathlib import Path

from app.domain.ports.git_port import GitPort
from app.infrastructure.parsing.models import ChunkMetadataCandidate, ParsedFile
from app.infrastructure.parsing.registry import ParserRegistry


class MetadataExtractor:
    """Ties a parsed file's symbols together with per-symbol `git blame`
    lookups (via Module 6's GitPort), producing the candidates Module 8's
    chunker hands off to for actual chunking. The same import list is
    attached to every symbol in the file — imports are file-scoped, not
    re-derived per symbol.
    """

    def __init__(self, git_port: GitPort) -> None:
        self._git_port = git_port

    async def extract(
        self, parsed: ParsedFile, repo_path: Path, relative_file_path: str
    ) -> list[ChunkMetadataCandidate]:
        parser = ParserRegistry.get_by_language_id(parsed.language_id)
        symbols = parser.extract_symbols(parsed)
        imports = tuple(parser.extract_imports(parsed))

        candidates: list[ChunkMetadataCandidate] = []
        for symbol in symbols:
            blame = tuple(
                await self._git_port.get_blame(
                    repo_path, relative_file_path, symbol.start_line, symbol.end_line
                )
            )
            candidates.append(ChunkMetadataCandidate(symbol=symbol, imports=imports, blame=blame))
        return candidates
