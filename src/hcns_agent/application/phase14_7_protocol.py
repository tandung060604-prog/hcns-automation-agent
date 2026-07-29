"""Safety helpers for the Phase 14.7 blinded OCR benchmark.

The prediction artifact is private and immutable once Ground Truth review
starts.  Review payloads intentionally contain no recognizer output so a human
reviewer can transcribe from pixels without annotation bias.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CROP_PROFILE = "bbox_balanced_64"
PENDING = "PENDING_REVIEW"
CONFIRMED = "CONFIRMED"
SKIPPED = "SKIPPED"
REVIEW_STATUSES = frozenset({PENDING, CONFIRMED, SKIPPED})
PREDICTION_PROFILES = (
    "paddle_detector_raw",
    "vietocr_vgg_seq2seq",
    "vietocr_vgg_transformer",
)

_FORBIDDEN_REVIEW_KEYS = frozenset(
    {
        "prediction",
        "predictions",
        "draft",
        "drafttranscription",
        "drafttext",
        "recognizedtext",
        "rawtext",
        "suggestion",
        "suggestions",
    }
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(
            json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def bbox_balanced_bounds(
    box: Sequence[Sequence[float]],
    *,
    image_width: int,
    image_height: int,
    pad_x_ratio: float = 0.18,
    pad_y_ratio: float = 0.12,
) -> tuple[int, int, int, int]:
    """Return the locked bbox_balanced_64 crop bounds."""

    if len(box) != 4 or any(len(point) != 2 for point in box):
        raise ValueError("Expected a four-point detector box")
    xs = [float(point[0]) for point in box]
    ys = [float(point[1]) for point in box]
    line_height = max(1.0, max(ys) - min(ys))
    pad_x = max(2, round(line_height * pad_x_ratio))
    pad_y = max(2, round(line_height * pad_y_ratio))
    left = max(0, int(min(xs)) - pad_x)
    right = min(image_width, int(max(xs)) + pad_x)
    top = max(0, int(min(ys)) - pad_y)
    bottom = min(image_height, int(max(ys)) + pad_y)
    if right <= left or bottom <= top:
        raise ValueError("Invalid crop bounds")
    return left, top, right, bottom


def queue_identity(case: Mapping[str, Any]) -> dict[str, str]:
    return {
        "caseId": str(case.get("caseId", "")),
        "documentId": str(case.get("documentId", "")),
        "cropSha256": str(case.get("cropSha256", "")),
    }


def compute_queue_digest(cases: Sequence[Mapping[str, Any]]) -> str:
    identities = [queue_identity(case) for case in cases]
    return hashlib.sha256(canonical_json_bytes(identities)).hexdigest()


def contains_forbidden_review_data(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = "".join(ch for ch in str(key).casefold() if ch.isalnum())
            if normalized in _FORBIDDEN_REVIEW_KEYS:
                return True
            if contains_forbidden_review_data(child):
                return True
        return False
    if isinstance(value, list):
        return any(contains_forbidden_review_data(child) for child in value)
    return False


def validate_review_queue(queue: Mapping[str, Any]) -> None:
    if queue.get("predictionsVisibleDuringReview") is not False:
        raise ValueError("Review queue must explicitly hide predictions")
    cases = queue.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Review queue has no cases")
    if int(queue.get("lineCount", -1)) != len(cases):
        raise ValueError("Review queue line count mismatch")
    if contains_forbidden_review_data(cases):
        raise ValueError("Review queue contains recognizer output")

    case_ids: set[str] = set()
    for case in cases:
        case_id = str(case.get("caseId", ""))
        if not case_id or case_id in case_ids:
            raise ValueError("Review case IDs must be unique and non-empty")
        if str(case.get("status", "")) not in REVIEW_STATUSES:
            raise ValueError("Review queue contains an invalid status")
        case_ids.add(case_id)

    expected_digest = compute_queue_digest(cases)
    if queue.get("queueDigest") != expected_digest:
        raise ValueError("Review queue digest mismatch")


def next_pending_case(queue: Mapping[str, Any]) -> Mapping[str, Any] | None:
    validate_review_queue(queue)
    for case in queue["cases"]:
        if isinstance(case, Mapping) and case.get("status") == PENDING:
            return case
    return None


def apply_review_update(
    queue: dict[str, Any],
    *,
    case_id: str,
    status: str,
    transcription: str,
    reviewer: str,
    reviewed_at: str,
) -> None:
    validate_review_queue(queue)
    if status not in {CONFIRMED, SKIPPED}:
        raise ValueError("Review update status must be CONFIRMED or SKIPPED")
    normalized_text = unicodedata.normalize("NFC", transcription.strip())
    if status == CONFIRMED and not normalized_text:
        raise ValueError("Confirmed transcription must not be empty")

    for case in queue["cases"]:
        if case["caseId"] != case_id:
            continue
        if case["status"] != PENDING:
            raise ValueError("A reviewed case cannot be overwritten")
        case["status"] = status
        case["confirmedTranscription"] = (
            normalized_text if status == CONFIRMED else ""
        )
        case["reviewer"] = reviewer.strip() or "local-reviewer"
        case["reviewedAt"] = reviewed_at
        return
    raise KeyError("Review case not found")


def review_progress(queue: Mapping[str, Any]) -> dict[str, int]:
    validate_review_queue(queue)
    counts = {status: 0 for status in REVIEW_STATUSES}
    for case in queue["cases"]:
        counts[str(case["status"])] += 1
    return {
        "total": len(queue["cases"]),
        "pending": counts[PENDING],
        "confirmed": counts[CONFIRMED],
        "skipped": counts[SKIPPED],
        "reviewed": counts[CONFIRMED] + counts[SKIPPED],
    }


def public_review_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Return the only fields allowed through the Ground Truth review API."""

    return {
        "caseId": case["caseId"],
        "documentId": case["documentId"],
        "pageIndex": int(case["pageIndex"]),
        "lineIndex": int(case["lineIndex"]),
        "cropPath": case["cropPath"],
        "pageRenderPath": case["pageRenderPath"],
        "box": case["box"],
        "cropSha256": case["cropSha256"],
    }


def verify_hidden_snapshot(
    *,
    queue: Mapping[str, Any],
    status: Mapping[str, Any],
    private_artifact_path: Path,
    lock_text: str,
) -> None:
    validate_review_queue(queue)
    if status.get("status") != "BLINDED_PREDICTIONS_READY":
        raise ValueError("Hidden predictions are not ready")
    if status.get("predictionsHiddenDuringReview") is not True:
        raise ValueError("Hidden-prediction evidence is missing")
    if status.get("queueDigest") != queue.get("queueDigest"):
        raise ValueError("Hidden predictions and review queue differ")
    if int(status.get("lineCount", -1)) != int(queue["lineCount"]):
        raise ValueError("Hidden prediction line count mismatch")

    artifact_digest = sha256_file(private_artifact_path)
    if status.get("privateArtifactSha256") != artifact_digest:
        raise ValueError("Hidden prediction artifact hash mismatch")
    expected_lock_line = (
        f"{artifact_digest}  predictions/{private_artifact_path.name}"
    )
    if lock_text.strip() != expected_lock_line:
        raise ValueError("Hidden prediction lock does not match artifact")
