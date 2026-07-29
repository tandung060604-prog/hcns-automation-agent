from __future__ import annotations

import json
from pathlib import Path

import pytest

from hcns_agent.application.phase16_heldout import (
    CONFIRMED,
    FAMILY_SPECS,
    LOCKED_POLICY_DIGEST,
    PARSER_VERSION,
    audit_sources,
    authorization_template,
    evaluate_once,
    prepare_manifest,
    seal_predictions,
)


def _write_sources(root: Path) -> None:
    for family, spec in FAMILY_SPECS.items():
        folder = root / "source" / str(spec["directory"])
        folder.mkdir(parents=True)
        for index in range(int(spec["minimum"])):
            (folder / f"{family}-{index}.png").write_bytes(
                f"{family}-{index}".encode()
            )


def test_audit_requires_every_family_and_rejects_seen_hash(tmp_path: Path) -> None:
    _write_sources(tmp_path)
    complete = audit_sources(tmp_path)
    assert complete["readyToPrepare"] is True

    first_hash = complete["documents"][0]["sourceSha256"]
    duplicate = audit_sources(tmp_path, known_hashes={first_hash})
    assert duplicate["readyToPrepare"] is False
    assert duplicate["duplicateKnownCount"] == 1


def test_prepare_requires_rights_and_never_exposes_predictions(tmp_path: Path) -> None:
    _write_sources(tmp_path)
    audit = audit_sources(tmp_path)
    authorization = authorization_template()
    with pytest.raises(ValueError, match="rights"):
        prepare_manifest(tmp_path, authorization, audit)

    authorization.update(
        {
            "processingRightsConfirmed": True,
            "documentOwnerConsentOrLawfulBasisConfirmed": True,
            "rightsBasis": "synthetic test fixture",
        }
    )
    manifest, queue = prepare_manifest(tmp_path, authorization, audit)
    rendered = json.dumps(queue)

    assert manifest["documentCount"] == 15
    assert queue["predictionsVisibleDuringReview"] is False
    assert '"predictions":' not in rendered.casefold()
    assert "recognizedtext" not in rendered.casefold()


def test_seal_rejects_ground_truth_and_wrong_policy(tmp_path: Path) -> None:
    _write_sources(tmp_path)
    authorization = authorization_template()
    authorization.update(
        {
            "processingRightsConfirmed": True,
            "documentOwnerConsentOrLawfulBasisConfirmed": True,
            "rightsBasis": "synthetic test fixture",
        }
    )
    manifest, _ = prepare_manifest(
        tmp_path,
        authorization,
        audit_sources(tmp_path),
    )
    predictions = {
        "datasetDigest": manifest["datasetDigest"],
        "recognitionPolicyDigest": "sha256:wrong",
        "parserVersion": PARSER_VERSION,
        "documents": [
            {"documentId": document["documentId"]}
            for document in manifest["documents"]
        ],
    }
    with pytest.raises(ValueError, match="locked Phase 14.8"):
        seal_predictions(predictions, manifest)

    predictions["recognitionPolicyDigest"] = LOCKED_POLICY_DIGEST
    predictions["groundTruth"] = {"leak": True}
    with pytest.raises(ValueError, match="must not contain Ground Truth"):
        seal_predictions(predictions, manifest)


def test_evaluation_is_aggregate_only_and_blocks_false_acceptance() -> None:
    sealed = {
        "predictionsHiddenDuringReview": True,
        "datasetDigest": "sha256:test",
        "documents": [
            {
                "documentId": "H16-CV-001",
                "documentFamily": "CV",
                "fields": {
                    "fullName": {
                        "value": "SAI",
                        "normalizedValue": "SAI",
                        "status": "accepted",
                    }
                },
            }
        ],
    }
    ground_truth = {
        "datasetDigest": "sha256:test",
        "groundTruthStatus": "USER_CONFIRMED_HELD_OUT_GROUND_TRUTH",
        "predictionsVisibleDuringReview": False,
        "documents": [
            {
                "documentId": "H16-CV-001",
                "documentFamily": "CV",
                "fields": {
                    "fullName": {"status": CONFIRMED, "value": "ĐÚNG"},
                },
            }
        ],
    }

    result = evaluate_once(sealed, ground_truth)

    assert result["evaluationRunCount"] == 1
    assert result["sensitiveFieldFalseAcceptanceCount"] == 1
    assert result["decision"]["controlledPilot"] == "NOT_PROMOTED"
    assert "ĐÚNG" not in json.dumps(result, ensure_ascii=False)
