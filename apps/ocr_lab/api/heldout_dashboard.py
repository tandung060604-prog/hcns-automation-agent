"""Local-only accessors for the real HR held-out evidence dashboard."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DOCUMENT_ID_RE = re.compile(r"^H16-[A-Z]+-\d{3}$")
INLINE_SOURCE_SUFFIXES = {".jpg", ".jpeg", ".png", ".pdf"}
SCHEMA_BY_FAMILY = {
    "CV": "schemas/hr_document_families/cv.schema.json",
    "ADMINISTRATIVE_REQUEST": (
        "schemas/hr_document_families/administrative_request.schema.json"
    ),
    "CONTRACT_DECISION": (
        "schemas/hr_document_families/contract_decision.schema.json"
    ),
    "DEGREE_CERTIFICATE": (
        "schemas/hr_document_families/degree_certificate.schema.json"
    ),
    "EMPLOYEE_FORM_TABLE": (
        "schemas/hr_document_families/employee_form_table.schema.json"
    ),
}


def resolve_heldout_root(
    data_root: Path,
    configured_root: Path | None,
) -> Path | None:
    """Resolve an explicitly configured root or the standard private sibling."""
    candidate = (
        configured_root
        if configured_root is not None
        else data_root.parent / "paddleocr-hr-heldout-v1"
    )
    resolved = candidate.expanduser().resolve()
    return resolved if resolved.is_dir() else None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    try:
        return _load_json(path) if path.is_file() else None
    except (OSError, json.JSONDecodeError):
        return None


def load_heldout_dashboard(root: Path) -> dict[str, Any]:
    """Return aggregate metrics and non-PII document metadata for localhost."""
    authorization = _load_json(root / "authorization.json")
    manifest = _load_json(root / "manifest_private.json")
    report = _load_json(root / "reports" / "PHASE16_HELDOUT_RESULTS.json")
    locked_replay = _load_optional_json(
        root
        / "predictions"
        / "latest_replay_private"
        / "latest_replay_evaluation.json"
    )
    live_v5_replay = _load_optional_json(
        root
        / "predictions"
        / "latest_live_v5_replay_private"
        / "latest_live_v5_evaluation.json"
    )
    if authorization.get("processingRightsConfirmed") is not True:
        raise PermissionError("Held-out processing rights are not confirmed")
    if authorization.get("authorizedLocalDocumentsOnly") is not True:
        raise PermissionError("Held-out corpus is not authorized for local access")

    documents = []
    for item in manifest.get("documents", []):
        document_id = str(item.get("documentId", ""))
        if not DOCUMENT_ID_RE.fullmatch(document_id):
            continue
        relative_source = Path(str(item.get("sourcePath", "")))
        if relative_source.is_absolute() or ".." in relative_source.parts:
            continue
        source_path = (root / relative_source).resolve()
        preview_path = source_path
        if source_path.suffix.lower() not in INLINE_SOURCE_SUFFIXES:
            rendered_page = (
                root
                / "predictions"
                / "private_work"
                / "pages"
                / document_id
                / "page_001.png"
            ).resolve()
            preview_path = rendered_page
        documents.append(
            {
                "documentId": document_id,
                "documentFamily": item.get("documentFamily"),
                "sourceFormat": item.get("sourceFormat"),
                "sizeBytes": item.get("sizeBytes"),
                "previewAvailable": preview_path.is_file(),
                "sourceAvailable": source_path.is_file(),
            }
        )

    public_release_authorized = all(
        authorization.get(key) is True
        for key in (
            "publicDisclosureApproved",
            "publicRedistributionRightsConfirmed",
            "piiSubjectsConsentForPublicReleaseConfirmed",
        )
    )
    return {
        "schemaVersion": "ocr-lab-real-heldout-dashboard/1.0.0",
        "datasetId": manifest.get("datasetId"),
        "datasetDigest": manifest.get("datasetDigest"),
        "containsRealPII": manifest.get("containsRealPII") is True,
        "localAccessAuthorized": True,
        "publicReleaseAuthorized": public_release_authorized,
        "predictionsVisibleDuringGroundTruthReview": manifest.get(
            "predictionsVisibleDuringGroundTruthReview"
        ),
        "recognitionPolicyDigest": report.get("recognitionPolicyDigest"),
        "parserVersion": report.get("parserVersion"),
        "metricSpecVersion": report.get("metricSpecVersion"),
        "evaluatedAt": report.get("evaluatedAt"),
        "evaluationRunCount": report.get("evaluationRunCount"),
        "thresholdRetuned": report.get("thresholdRetuned"),
        "predictionsWereHidden": report.get("predictionsWereHidden"),
        "documentCount": report.get("documentCount"),
        "countsByFamily": manifest.get("countsByFamily", {}),
        "overall": report.get("overall", {}),
        "byFamily": report.get("byFamily", {}),
        "sensitiveFieldFalseAcceptanceCount": report.get(
            "sensitiveFieldFalseAcceptanceCount"
        ),
        "decision": report.get("decision", {}),
        "latestReplay": locked_replay,
        "latestLiveV5Replay": live_v5_replay,
        "documents": documents,
    }


def resolve_heldout_document(
    root: Path,
    document_id: str,
    *,
    preview: bool,
) -> tuple[Path, dict[str, Any]]:
    """Resolve one manifest-owned file without allowing path traversal."""
    if not DOCUMENT_ID_RE.fullmatch(document_id):
        raise ValueError("Invalid held-out document id")
    manifest = _load_json(root / "manifest_private.json")
    item = next(
        (
            row
            for row in manifest.get("documents", [])
            if row.get("documentId") == document_id
        ),
        None,
    )
    if item is None:
        raise FileNotFoundError("Held-out document not found")
    relative_source = Path(str(item.get("sourcePath", "")))
    if relative_source.is_absolute() or ".." in relative_source.parts:
        raise ValueError("Unsafe held-out source path")
    source_path = (root / relative_source).resolve()
    if root.resolve() not in source_path.parents:
        raise ValueError("Unsafe held-out source path")
    selected_path = source_path
    if preview and source_path.suffix.lower() not in INLINE_SOURCE_SUFFIXES:
        selected_path = (
            root
            / "predictions"
            / "private_work"
            / "pages"
            / document_id
            / "page_001.png"
        ).resolve()
    if root.resolve() not in selected_path.parents or not selected_path.is_file():
        raise FileNotFoundError("Held-out document preview not found")
    return selected_path, item


def load_heldout_document_evidence(
    root: Path,
    document_id: str,
) -> dict[str, Any]:
    """Return one document's private Ground Truth and sealed prediction locally."""
    if not DOCUMENT_ID_RE.fullmatch(document_id):
        raise ValueError("Invalid held-out document id")
    authorization = _load_json(root / "authorization.json")
    if authorization.get("processingRightsConfirmed") is not True:
        raise PermissionError("Held-out processing rights are not confirmed")
    if authorization.get("authorizedLocalDocumentsOnly") is not True:
        raise PermissionError("Held-out corpus is not authorized for local access")

    ground_truth = _load_json(
        root / "ground_truth" / "ground_truth_confirmed_private.json"
    )
    sealed_predictions = _load_json(
        root / "predictions" / "sealed_predictions_private.json"
    )
    locked_replay_predictions = _load_optional_json(
        root
        / "predictions"
        / "latest_replay_private"
        / "latest_replay_predictions_private.json"
    )
    live_v5_predictions = _load_optional_json(
        root
        / "predictions"
        / "latest_live_v5_replay_private"
        / "latest_live_v5_predictions_private.json"
    )
    ground_truth_document = next(
        (
            item
            for item in ground_truth.get("documents", [])
            if item.get("documentId") == document_id
        ),
        None,
    )
    sealed_prediction_document = next(
        (
            item
            for item in sealed_predictions.get("documents", [])
            if item.get("documentId") == document_id
        ),
        None,
    )
    locked_replay_document = next(
        (
            item
            for item in (locked_replay_predictions or {}).get("documents", [])
            if item.get("documentId") == document_id
        ),
        None,
    )
    live_v5_document = next(
        (
            item
            for item in (live_v5_predictions or {}).get("documents", [])
            if item.get("documentId") == document_id
        ),
        None,
    )
    if ground_truth_document is None or sealed_prediction_document is None:
        raise FileNotFoundError("Held-out evidence not found")

    prediction_document = (
        live_v5_document
        or locked_replay_document
        or sealed_prediction_document
    )
    family = str(
        prediction_document.get("documentFamily")
        or ground_truth_document.get("documentFamily")
        or "OTHER_HR_DOCUMENT"
    )
    return {
        "schemaVersion": "ocr-lab-real-heldout-evidence/1.0.0",
        "documentId": document_id,
        "documentFamily": family,
        "documentType": prediction_document.get("documentType"),
        "schemaRef": SCHEMA_BY_FAMILY.get(
            family,
            "schemas/business_document.schema.json",
        ),
        "containsRealPII": True,
        "localOnly": True,
        "groundTruth": ground_truth_document,
        "prediction": prediction_document,
        "sealedPrediction": sealed_prediction_document,
        "lockedReplayPrediction": locked_replay_document,
        "liveV5Prediction": live_v5_document,
        "predictionProvenance": {
            "defaultSource": (
                "live_v5"
                if live_v5_document is not None
                else (
                    "locked_replay"
                    if locked_replay_document is not None
                    else "sealed"
                )
            ),
            "sealed": {
                "sealedAt": sealed_predictions.get("sealedAt"),
                "parserVersion": sealed_predictions.get("parserVersion"),
                "recognitionPolicyDigest": sealed_predictions.get(
                    "recognitionPolicyDigest"
                ),
                "evaluationKind": "BLINDED_EVALUATE_ONCE",
            },
            "lockedReplay": (
                {
                    "createdAt": locked_replay_predictions.get("createdAt"),
                    "parserVersion": locked_replay_predictions.get(
                        "parserVersion"
                    ),
                    "recognitionPolicyDigest": locked_replay_predictions.get(
                        "recognitionPolicyDigest"
                    ),
                    "evaluationKind": locked_replay_predictions.get(
                        "evaluationKind"
                    ),
                    "promotionEligible": locked_replay_predictions.get(
                        "promotionEligible"
                    ),
                }
                if locked_replay_document is not None
                else None
            ),
            "liveV5": (
                {
                    "createdAt": live_v5_predictions.get("createdAt"),
                    "parserVersion": live_v5_predictions.get(
                        "parserVersion"
                    ),
                    "recognitionPolicyDigest": live_v5_predictions.get(
                        "recognitionPolicyDigest"
                    ),
                    "evaluationKind": live_v5_predictions.get(
                        "evaluationKind"
                    ),
                    "promotionEligible": live_v5_predictions.get(
                        "promotionEligible"
                    ),
                    "ocrPipeline": live_v5_predictions.get("ocrPipeline"),
                }
                if live_v5_document is not None
                else None
            ),
        },
    }
