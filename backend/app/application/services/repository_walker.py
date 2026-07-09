import os
from collections.abc import Iterator
from pathlib import Path

import pathspec


def walk_repository(
    root: Path,
    *,
    max_file_size_bytes: int,
    excluded_dir_names: frozenset[str],
) -> Iterator[tuple[Path, str]]:
    """Yields `(absolute_path, relative_posix_path)` for every file worth
    indexing under `root` — respecting `.gitignore` (if present at the
    repo root; nested `.gitignore` files are not consulted, matching the
    single-pass simplicity of `git ls-files` without a real git index),
    pruning built-in noise directories before ever descending into them
    (not just filtering their contents after the fact — `node_modules`
    alone can hold hundreds of thousands of files), and skipping symlinks
    (avoids escaping `root` or infinite loops from a self-referential
    link) and anything over `max_file_size_bytes`.
    """
    gitignore_path = root / ".gitignore"
    spec = (
        pathspec.PathSpec.from_lines("gitwildmatch", gitignore_path.read_text().splitlines())
        if gitignore_path.is_file()
        else pathspec.PathSpec.from_lines("gitwildmatch", [])
    )

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in excluded_dir_names]

        for filename in filenames:
            absolute_path = Path(dirpath) / filename
            if absolute_path.is_symlink():
                continue

            relative_path = absolute_path.relative_to(root).as_posix()
            if spec.match_file(relative_path):
                continue

            try:
                size = absolute_path.stat().st_size
            except OSError:
                continue  # e.g. a broken symlink target, or removed mid-walk
            if size > max_file_size_bytes:
                continue

            yield absolute_path, relative_path
