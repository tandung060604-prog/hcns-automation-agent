"""Run the local synthetic M4-CAM-006 matrix and print aggregate evidence."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))



def _run() -> int:
    from hcns_agent.adapters.camunda7.dry_run import main

    return main()


if __name__ == "__main__":
    raise SystemExit(_run())
