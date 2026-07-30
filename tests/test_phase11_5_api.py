from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from serve_dashboard_api import resolve_phase11_5_crop  # noqa: E402


def test_phase11_5_crop_resolution_stays_inside_private_data(tmp_path: Path) -> None:
    data_root = tmp_path / "private"
    session_dir = data_root / "output" / "user_sessions" / "session"
    evidence_dir = session_dir / "phase11_5"
    crop_path = data_root / "output" / "phase11_5_private" / "full_name.png"
    crop_path.parent.mkdir(parents=True)
    crop_path.write_bytes(b"png")
    evidence_dir.mkdir(parents=True)
    evidence_path = evidence_dir / "field_consensus.json"
    evidence_path.write_text(
        json.dumps(
            {
                "crops": {
                    "fullName": {
                        "balanced_padding": {
                            "path": str(crop_path),
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert (
        resolve_phase11_5_crop(
            data_root,
            session_dir,
            "fullName",
            "balanced_padding",
        )
        == crop_path.resolve()
    )

    outside_path = tmp_path / "outside.png"
    outside_path.write_bytes(b"png")
    evidence_path.write_text(
        json.dumps(
            {
                "crops": {
                    "fullName": {
                        "balanced_padding": {
                            "path": str(outside_path),
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    assert (
        resolve_phase11_5_crop(
            data_root,
            session_dir,
            "fullName",
            "balanced_padding",
        )
        is None
    )
