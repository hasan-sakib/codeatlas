from pathlib import Path

from app.application.services.repository_walker import walk_repository

_EXCLUDED_DIR_NAMES = frozenset({".git", "node_modules", "__pycache__"})


def _relative_paths(root: Path, **kwargs: object) -> set[str]:
    return {
        rel
        for _, rel in walk_repository(
            root,
            max_file_size_bytes=kwargs.get("max_file_size_bytes", 1_000_000),  # type: ignore[arg-type]
            excluded_dir_names=kwargs.get("excluded_dir_names", _EXCLUDED_DIR_NAMES),  # type: ignore[arg-type]
        )
    }


def test_walk_repository_respects_gitignore(tmp_path: Path) -> None:
    (tmp_path / "keep.py").write_text("x = 1\n")
    (tmp_path / "skip.py").write_text("y = 2\n")
    (tmp_path / ".gitignore").write_text("skip.py\n")

    assert _relative_paths(tmp_path) == {"keep.py", ".gitignore"}


def test_walk_repository_prunes_excluded_directories_without_descending(tmp_path: Path) -> None:
    (tmp_path / "keep.py").write_text("x = 1\n")
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    (node_modules / "dep.js").write_text("var x;\n")
    nested = node_modules / "nested"
    nested.mkdir()
    (nested / "deep.js").write_text("var y;\n")

    assert _relative_paths(tmp_path, excluded_dir_names=frozenset({"node_modules"})) == {"keep.py"}


def test_walk_repository_skips_oversized_files(tmp_path: Path) -> None:
    (tmp_path / "small.py").write_text("x = 1\n")
    (tmp_path / "big.py").write_text("x" * 100)

    assert _relative_paths(tmp_path, max_file_size_bytes=10) == {"small.py"}


def test_walk_repository_skips_symlinks(tmp_path: Path) -> None:
    real_file = tmp_path / "real.py"
    real_file.write_text("x = 1\n")
    (tmp_path / "link.py").symlink_to(real_file)

    assert _relative_paths(tmp_path) == {"real.py"}


def test_walk_repository_with_no_gitignore_present(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")

    assert _relative_paths(tmp_path) == {"a.py", "b.py"}


def test_walk_repository_yields_nested_paths_as_posix(tmp_path: Path) -> None:
    nested = tmp_path / "pkg" / "sub"
    nested.mkdir(parents=True)
    (nested / "mod.py").write_text("x = 1\n")

    assert _relative_paths(tmp_path) == {"pkg/sub/mod.py"}
