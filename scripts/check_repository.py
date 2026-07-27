"""Fast repository hygiene checks that do not inspect private data."""

from __future__ import annotations

import os
from pathlib import Path

REQUIRED_FILES = (
    "README.md",
    "AGENTS.md",
    "docs/PROJECT_STATE.md",
    "docs/ARCHITECTURE.md",
    "docs/HUMAN_IN_THE_LOOP.md",
    "docs/MODEL_GUIDE.md",
    "schemas/business_document.schema.json",
)

FORBIDDEN_TRACKED_PARTS = {
    ".env",
    "data/private",
    "data/uploads",
    "outputs",
    "models",
}

SKIPPED_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dataset",
}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    missing = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    if missing:
        raise SystemExit(f"Missing required files: {', '.join(missing)}")

    violations: list[str] = []
    for current_root, directory_names, file_names in os.walk(root, topdown=True):
        current = Path(current_root)
        retained_directories: list[str] = []
        for name in directory_names:
            relative_directory = (current / name).relative_to(root).as_posix()
            if name in SKIPPED_DIRECTORY_NAMES:
                continue
            if relative_directory in FORBIDDEN_TRACKED_PARTS or any(
                relative_directory.startswith(f"{part}/")
                for part in FORBIDDEN_TRACKED_PARTS
            ):
                violations.append(relative_directory)
                continue
            retained_directories.append(name)
        directory_names[:] = sorted(retained_directories)
        for file_name in file_names:
            relative = (current / file_name).relative_to(root).as_posix()
            if relative in FORBIDDEN_TRACKED_PARTS or any(
                relative.startswith(f"{part}/") for part in FORBIDDEN_TRACKED_PARTS
            ):
                violations.append(relative)
    if violations:
        raise SystemExit(f"Forbidden repository content: {', '.join(violations)}")

    print("Repository hygiene checks passed")


if __name__ == "__main__":
    main()
