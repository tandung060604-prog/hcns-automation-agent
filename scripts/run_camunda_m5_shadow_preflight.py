"""Run the local-only synthetic M5-CAM-001A Camunda preflight."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hcns_agent.adapters.camunda7.shadow_preflight import (  # noqa: E402
    build_local_shadow_gateway,
    run_shadow_preflight,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run two synthetic leave/overtime cases through local Camunda 7.13."
    )
    parser.add_argument("--camunda-url", required=True)
    parser.add_argument("--worker-id", default="m5-shadow-preflight")
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.output.is_absolute():
        raise ValueError("--output must be an absolute private path")
    output = args.output.resolve()
    if ROOT in output.parents:
        raise ValueError("--output must be outside the repository")
    if output.exists():
        raise FileExistsError("--output already exists; preflight reports are create-only")
    report = run_shadow_preflight(
        gateway=build_local_shadow_gateway(
            base_url=args.camunda_url,
            worker_id=args.worker_id,
        ),
        private_root=args.private_root,
        repository_root=ROOT,
        worker_id=args.worker_id,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
