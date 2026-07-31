"""Build a reproducible, PII-safe CCCD evidence selection for the weekly report.

The input remains under the operator-supplied private data root.  Output contains
only opaque sample IDs, operational metadata and a deterministic ranking score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

RANKING_VERSION = "cccd-evidence-ranking/1.0"


def opaque_id(session_id: str) -> str:
    """Return a non-reversible report identifier without preserving session IDs."""

    return f"CCCD-EV-{hashlib.sha256(session_id.encode('utf-8')).hexdigest()[:10].upper()}"


def ranking_score(result: dict[str, Any], reviewed: bool) -> tuple[float, dict[str, float]]:
    """Rank review-complete cases without inspecting field values or OCR text."""

    document = result.get("document", {})
    processing = result.get("processing", {})
    phase11 = result.get("phase11", {})
    confidence = float(document.get("avgConfidence") or 0.0)
    components = {
        "review_complete": 100.0 if reviewed else 0.0,
        "ocr_success": 20.0 if document.get("ocrSuccess") else 0.0,
        "phase11_present": 10.0 if phase11 else 0.0,
        "confidence": round(max(0.0, min(confidence, 1.0)) * 10.0, 3),
        "duration_penalty": -min(float(processing.get("totalDurationMs") or 0.0) / 60000.0, 2.0),
    }
    return round(sum(components.values()), 3), components


def build_selection(data_root: Path, limit: int) -> dict[str, Any]:
    sessions_root = data_root / "user_uploads" / "sessions"
    candidates: list[dict[str, Any]] = []
    for result_path in sorted(sessions_root.glob("*/result.json")):
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if result.get("document", {}).get("documentType") != "IDENTITY_DOCUMENT":
            continue
        review_path = result_path.parent / "phase10" / "ground_truth.json"
        try:
            assertions = json.loads(review_path.read_text(encoding="utf-8")).get(
                "verificationAssertions", {}
            )
        except (OSError, json.JSONDecodeError):
            assertions = {}
        reviewed = bool(assertions.get("comparedWithImage") and assertions.get("allTextChecked"))
        if not reviewed:
            continue
        score, components = ranking_score(result, reviewed)
        document = result.get("document", {})
        candidates.append(
            {
                "sampleId": opaque_id(str(result.get("sessionId", ""))),
                "score": score,
                "scoreComponents": components,
                "format": result.get("source", {}).get("format", "unknown"),
                "pageCount": result.get("source", {}).get("pageCount", 0),
                "recognizedTextLineCount": document.get("recognizedTextLineCount", 0),
                "qualityGate": result.get("phase9", {}).get("qualityGate", {}).get("status"),
                "phase11Version": result.get("phase11", {}).get("version"),
            }
        )
    candidates.sort(key=lambda item: (-item["score"], item["sampleId"]))
    return {
        "schemaVersion": "weekly-report-cccd-selection/1.0",
        "rankingVersion": RANKING_VERSION,
        "selectionRule": (
            "review-complete identity documents, sorted by score descending then opaque ID"
        ),
        "privacy": {
            "containsPII": False,
            "containsRawOcrText": False,
            "containsOriginalFileNames": False,
            "sampleIdDerivation": "SHA-256(session_id), truncated to 10 hexadecimal characters",
        },
        "eligibleCount": len(candidates),
        "selected": candidates[:limit],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=4)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    selection = build_selection(args.data_root, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(selection, ensure_ascii=False, indent=2) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    print(f"selected={len(selection['selected'])} eligible={selection['eligibleCount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
