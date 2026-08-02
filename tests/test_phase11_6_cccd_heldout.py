from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from scripts.phase11_6_cccd_heldout import (
    persist_phase11_5_snapshots,
    select_novel_sources,
    validate_authorization,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def image(path: Path, color: tuple[int, int, int]) -> str:
    Image.new("RGB", (32, 20), color).save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_select_novel_sources_excludes_development_and_duplicates(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    old_hash = image(source / "old.png", (10, 20, 30))
    novel_hash = image(source / "novel.png", (40, 50, 60))
    (source / "duplicate.png").write_bytes((source / "novel.png").read_bytes())

    selected = select_novel_sources(source, {old_hash})

    assert len(selected) == 1
    assert selected[0][1] == novel_hash


def test_authorization_must_be_explicit(tmp_path: Path) -> None:
    write_json(
        tmp_path / "authorization.json",
        {
            "authorizedLocalDocumentsOnly": True,
            "processingRightsConfirmed": False,
            "documentOwnerConsentOrLawfulBasisConfirmed": True,
            "rightsBasis": "synthetic fixture",
        },
    )

    with pytest.raises(PermissionError):
        validate_authorization(tmp_path)


def test_fresh_heldout_baseline_is_frozen_before_candidate(
    tmp_path: Path,
) -> None:
    session_id = "session-1"
    session = tmp_path / "user_uploads" / "sessions" / session_id
    payload = {"schemaVersion": "11.5.0", "fields": {}}
    write_json(
        session / "result.json",
        {
            "phase11_5": {"status": "COMPLETE"},
            "phase11": {"identityCard": payload},
        },
    )

    persist_phase11_5_snapshots(
        tmp_path,
        {"records": [{"sessionId": session_id}]},
    )

    assert json.loads(
        (session / "phase11_5" / "identity_card.json").read_text(
            encoding="utf-8"
        )
    ) == payload


def test_heldout_baseline_snapshot_cannot_change(
    tmp_path: Path,
) -> None:
    session_id = "session-1"
    session = tmp_path / "user_uploads" / "sessions" / session_id
    write_json(
        session / "result.json",
        {
            "phase11_5": {"status": "COMPLETE"},
            "phase11": {
                "identityCard": {
                    "schemaVersion": "11.5.0",
                    "fields": {"fullName": "candidate"},
                }
            },
        },
    )
    write_json(
        session / "phase11_5" / "identity_card.json",
        {
            "schemaVersion": "11.5.0",
            "fields": {"fullName": "baseline"},
        },
    )

    with pytest.raises(ValueError, match="snapshot mismatch"):
        persist_phase11_5_snapshots(
            tmp_path,
            {"records": [{"sessionId": session_id}]},
        )
