from datetime import UTC, datetime
from pathlib import Path

from app.domain.value_objects.clone_result import BlameEntry, ClonedRepo
from app.infrastructure.parsing.metadata_extractor import MetadataExtractor
from app.infrastructure.parsing.parsers.python_parser import PythonParser

FIXTURE = b"def foo():\n    pass\n\n\ndef bar():\n    pass\n"


class FakeGitPort:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, str, int, int]] = []

    async def clone(self, url: str, dest_dir: Path, *, shallow: bool = True) -> ClonedRepo:
        raise NotImplementedError

    async def get_blame(
        self, repo_path: Path, file_path: str, start_line: int, end_line: int
    ) -> list[BlameEntry]:
        self.calls.append((repo_path, file_path, start_line, end_line))
        return [
            BlameEntry(
                author="Amina Dev",
                commit_sha="abc123",
                committed_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ]


async def test_extract_zips_each_symbol_to_its_own_blame_call() -> None:
    parser = PythonParser()
    parsed = parser.parse(FIXTURE)
    git_port = FakeGitPort()
    extractor = MetadataExtractor(git_port)

    candidates = await extractor.extract(parsed, Path("/repo"), "app.py")

    assert len(candidates) == 2
    assert git_port.calls == [
        (Path("/repo"), "app.py", 1, 2),
        (Path("/repo"), "app.py", 5, 6),
    ]
    assert candidates[0].symbol.name == "foo"
    assert candidates[0].blame[0].author == "Amina Dev"
    assert candidates[1].symbol.name == "bar"


async def test_extract_attaches_the_same_file_scoped_imports_to_every_candidate() -> None:
    source = b"import os\n\n\ndef foo():\n    pass\n\n\ndef bar():\n    pass\n"
    parser = PythonParser()
    parsed = parser.parse(source)
    extractor = MetadataExtractor(FakeGitPort())

    candidates = await extractor.extract(parsed, Path("/repo"), "app.py")

    assert len(candidates) == 2
    assert candidates[0].imports == candidates[1].imports
    assert candidates[0].imports[0].module == "os"
