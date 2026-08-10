"""Local Camunda 7 External Task worker entrypoint for the M4 shadow pilot."""

from __future__ import annotations

from hcns_agent.adapters.camunda7.runtime import build_m4_worker_from_environment


def main() -> int:
    worker = build_m4_worker_from_environment()
    try:
        worker.run_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
