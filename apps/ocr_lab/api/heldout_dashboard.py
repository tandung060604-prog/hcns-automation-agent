"""Local-only accessors for the real HR held-out evidence dashboard."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DOCUMENT_ID_RE = re.compile(r"^H16-[A-Z]+-\d{3}$")
INLINE_SOURCE_SUFFIXES = {".jpg", ".jpeg", ".png", ".pdf"}


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


def load_heldout_dashboard(root: Path) -> dict[str, Any]:
    """Return aggregate metrics and non-PII document metadata for localhost."""
    authorization = _load_json(root / "authorization.json")
    manifest = _load_json(root / "manifest_private.json")
    report = _load_json(root / "reports" / "PHASE16_HELDOUT_RESULTS.json")
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
