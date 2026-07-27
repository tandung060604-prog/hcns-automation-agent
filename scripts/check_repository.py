"""Fast repository hygiene checks that do not inspect private data."""

from __future__ import annotations

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


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    missing = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    if missing:
        raise SystemExit(f"Missing required files: {', '.join(missing)}")

    violations: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        if relative in FORBIDDEN_TRACKED_PARTS or any(
            relative.startswith(f"{part}/") for part in FORBIDDEN_TRACKED_PARTS
        ):
            violations.append(relative)
    if violations:
        raise SystemExit(f"Forbidden repository content: {', '.join(violations)}")

    print("Repository hygiene checks passed")


if __name__ == "__main__":
    main()

