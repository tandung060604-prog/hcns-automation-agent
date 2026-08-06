"""Validate the durable LongRun state against the current Git checkout."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DOCS = {
    "state": Path("docs/PROJECT_STATE.md"),
    "backlog": Path("docs/BACKLOG.md"),
    "handoff": Path("docs/HANDOFF.md"),
}
TASK_ID = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)+")


def backlog_rows(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or not TASK_ID.fullmatch(cells[0]):
            continue
        rows[cells[0]] = cells[1]
    return rows


def marker(text: str, label: str) -> str | None:
    match = re.search(rf"^-\s*{re.escape(label)}:\s*`?([^`\s]+)", text, re.MULTILINE)
    return match.group(1) if match else None


def git_value(root: Path, *args: str) -> tuple[str | None, str | None]:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    if result.returncode:
        return None, result.stderr.strip() or "git command failed"
    return result.stdout.strip(), None


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    contents: dict[str, str] = {}
    for name, relative in DOCS.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"missing {relative.as_posix()}")
        else:
            contents[name] = path.read_text(encoding="utf-8")

    state = contents.get("state", "")
    backlog = contents.get("backlog", "")
    handoff = contents.get("handoff", "")
    rows = backlog_rows(backlog)

    if len(state.splitlines()) > 80:
        errors.append("PROJECT_STATE.md must stay at or below 80 lines")
    if not re.search(r"^Current milestone:\s*\S+", state, re.MULTILINE):
        errors.append("PROJECT_STATE.md has no current milestone")
    if not re.search(r"^Next action:\s*\S+", state, re.MULTILINE):
        errors.append("PROJECT_STATE.md has no next action")
    if not re.search(r"^Archive:.*docs/archive/", state, re.MULTILINE):
        errors.append("PROJECT_STATE.md does not link an evidence archive")

    ready_ids = {task_id for task_id, status in rows.items() if status.startswith("READY")}
    next_task = re.search(r"^Next READY task:\s*`?([^`\s]+)", state, re.MULTILINE)
    if not next_task:
        errors.append("PROJECT_STATE.md has no next READY task")
    elif next_task.group(1) not in ready_ids:
        errors.append(f"next READY task {next_task.group(1)} is not READY in BACKLOG.md")

    checkpoint = re.search(r"^Checkpoint task:\s*`?([^`\s]+)", state, re.MULTILINE)
    if checkpoint and checkpoint.group(1) not in rows:
        errors.append(f"checkpoint task {checkpoint.group(1)} is missing from BACKLOG.md")

    actual_branch, branch_error = git_value(root, "rev-parse", "--abbrev-ref", "HEAD")
    actual_head, head_error = git_value(root, "rev-parse", "HEAD")
    if branch_error:
        errors.append(f"cannot read Git branch: {branch_error}")
    if head_error:
        errors.append(f"cannot read Git HEAD: {head_error}")

    handoff_branch = marker(handoff, "Branch")
    handoff_head = marker(handoff, "HEAD")
    state_branch = marker(state, "Branch")
    state_head = marker(state, "HEAD")
    if actual_branch and handoff_branch != actual_branch:
        errors.append(f"HANDOFF.md branch is {handoff_branch!r}, Git is {actual_branch!r}")
    if actual_branch and state_branch != actual_branch:
        errors.append(f"PROJECT_STATE.md branch is {state_branch!r}, Git is {actual_branch!r}")
    if actual_head and handoff_head != actual_head:
        errors.append("HANDOFF.md HEAD does not match Git HEAD")
    if actual_head and (not state_head or not actual_head.startswith(state_head)):
        errors.append("PROJECT_STATE.md HEAD does not match Git HEAD")

    handoff_next = re.search(r"^- Next READY task:\s*`?([^`\s]+)", handoff, re.MULTILINE)
    if next_task and (not handoff_next or handoff_next.group(1) != next_task.group(1)):
        errors.append("HANDOFF.md and PROJECT_STATE.md disagree on the next READY task")
    if not re.search(r"^## Current checkpoint \(", handoff, re.MULTILINE):
        errors.append("HANDOFF.md has no current checkpoint section")

    archive = root / "docs/archive/PROJECT_STATE_HISTORY_2026-08-06.md"
    if not archive.is_file():
        errors.append(f"missing {archive.relative_to(root).as_posix()}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    errors = validate(root)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("LongRun state consistency: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
