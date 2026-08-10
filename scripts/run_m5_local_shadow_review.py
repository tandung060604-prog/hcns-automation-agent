"""Run a metadata-only M5 local shadow review over an existing projection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hcns_agent.adapters.camunda7.local_shadow_review import (
    LocalShadowReviewError,
    load_projection,
    run_local_shadow_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a local prediction projection at the Camunda shadow boundary"
    )
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("refusing to overwrite an existing shadow report")
    try:
        report = run_local_shadow_review(load_projection(str(args.projection)))
    except (OSError, json.JSONDecodeError, LocalShadowReviewError) as error:
        raise SystemExit(f"M5-CAM-001D HOLD: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if report.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
