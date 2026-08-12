"""Fast repository hygiene checks that do not inspect private data."""

from __future__ import annotations

import subprocess
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

def _tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [path for path in result.stdout.decode("utf-8").split("\0") if path]


def _is_forbidden(path: str) -> bool:
    return path in FORBIDDEN_TRACKED_PARTS or any(
        path.startswith(f"{part}/") for part in FORBIDDEN_TRACKED_PARTS
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    missing = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    if missing:
        raise SystemExit(f"Missing required files: {', '.join(missing)}")

    violations = [path for path in _tracked_paths(root) if _is_forbidden(path)]
    if violations:
        raise SystemExit(f"Forbidden repository content: {', '.join(violations)}")

    print("Repository hygiene checks passed")


if __name__ == "__main__":
    main()
