#!/usr/bin/env python3
"""Score the sealed OCR-HO-V2 development replay without exporting PII."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_cccd_phase11_5 import evaluate_variant, value  # noqa: E402
from ocr_ho_v2_014_evaluation import aggregate, gates  # noqa: E402
from phase11_5_cccd import FIELD_ORDER  # noqa: E402

TARGET_FIELDS = ("fullName", "placeOfOrigin", "placeOfResidence")
PROTECTED_FIELDS = ("identityNumber", "dateOfBirth", "sex", "nationality", "dateOfExpiry")
CLASS_NAMES = (
    "ROI_MISS",
    "RECOGNIZER_MISS",
    "DIACRITIC_MISS",
    "SELECTOR_MISS",
    "PARSER_CONTAMINATION",
    "EXACT",
)
LABELS = (
    "full name",
    "place of origin",
    "place of residence",
    "date of expiry",
    "date of birth",
    "nationality",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized(text: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(text or "")).split()).casefold()


def ascii_normalized(text: Any) -> str:
    decomposed = unicodedata.normalize("NFD", str(text or "")).casefold()
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def contaminated(field: dict[str, Any], candidates: list[dict[str, Any]]) -> bool:
    signals = {str(signal) for signal in field.get("errorSignals", [])}
    if signals.intersection({"label_contamination", "region_or_line_merge"}):
        return True
    values = [field.get("value")] + [item.get("value") for item in candidates]
    return any(
        any(label in normalized(item) for label in LABELS)
        for item in values
        if item
    )


def classify(
    *, expected: str, field: dict[str, Any], candidates: list[dict[str, Any]], roi_hit: bool
) -> str:
    if not roi_hit:
        return "ROI_MISS"
    selected = normalized(field.get("value"))
    if selected == normalized(expected):
        return "EXACT"
    if contaminated(field, candidates):
        return "PARSER_CONTAMINATION"
    candidate_values = [normalized(item.get("value")) for item in candidates]
    if normalized(expected) in candidate_values:
        return "SELECTOR_MISS"
    if ascii_normalized(expected) in {ascii_normalized(item) for item in candidate_values}:
        return "DIACRITIC_MISS"
    return "RECOGNIZER_MISS"


def field_candidates(
    field: dict[str, Any], artifact: dict[str, Any], name: str
) -> list[dict[str, Any]]:
    candidates = artifact.get("candidates", {}).get(name)
    if isinstance(candidates, list):
        return [item for item in candidates if isinstance(item, dict)]
    return [
        item for item in (field.get("evidence", {}).get("candidates") or [])
        if isinstance(item, dict)
]


def make_documents(root: Path, sealed: dict[str, Any]) -> list[dict[str, Any]]:
    sessions = root / "user_uploads-sessions"
    documents: list[dict[str, Any]] = []
    for record in sealed["documents"]:
        session = sessions / str(record["sessionId"])
        baseline = json.loads(
            (session / "phase11_5" / "identity_card.json").read_text(encoding="utf-8")
        )
        candidate_artifact = json.loads(
            (session / "phase11_10_v2" / "field_consensus.json").read_text(encoding="utf-8")
        )
        result = json.loads((session / "result.json").read_text(encoding="utf-8"))
        documents.append({
            "groundTruth": {name: item["value"] for name, item in record["fields"].items()},
            "baseline": baseline.get("fields", {}),
            "phase11_10": candidate_artifact.get("identityCard", {}).get("fields", {}),
            "candidateArtifact": candidate_artifact,
            "gtFields": record["fields"],
            "durations": {
                "baseline": result.get("phase11_5", {}).get("durationMs", 0.0),
                "phase11_10": result.get("phase11_10_v2", {}).get("durationMs", 0.0),
            },
        })
    return documents


def class_report(documents: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    labels: list[tuple[str, str]] = []
    roi_hits: dict[str, int] = {name: 0 for name in TARGET_FIELDS}
    evaluated: dict[str, int] = {name: 0 for name in TARGET_FIELDS}
    for document in documents:
        artifact = document["candidateArtifact"]
        fields = document[variant]
        for name in TARGET_FIELDS:
            expected = str(document["groundTruth"].get(name) or "")
            field = fields.get(name) or {}
            if not expected:
                continue
            if variant == "phase11_10":
                gt_ids = set(document["gtFields"][name]["lineIds"])
                roi_ids = set((artifact.get("regions", {}).get(name) or {}).get("lineIds") or [])
                roi_hit = gt_ids.issubset(roi_ids)
            else:
                roi_hit = bool((field.get("evidence") or {}).get("bbox"))
            evaluated[name] += 1
            roi_hits[name] += int(roi_hit)
            candidates = (
                [
                    item for item in (field.get("evidence", {}).get("candidates") or [])
                    if isinstance(item, dict)
                ]
                if variant == "baseline"
                else field_candidates(field, artifact, name)
            )
            labels.append((name, classify(
                expected=expected, field=field, candidates=candidates, roi_hit=roi_hit
            )))
    return {
        "classCountsByField": aggregate(labels),
        "roiByField": {
            name: {
                "correct": roi_hits[name],
                "evaluated": evaluated[name],
                "accuracy": round(roi_hits[name] / max(1, evaluated[name]), 6),
            }
            for name in TARGET_FIELDS
        },
    }
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--sealed-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    root = args.data_root.resolve()
    sealed_path = args.sealed_manifest.resolve()
    sealed = json.loads(sealed_path.read_text(encoding="utf-8"))
    if sealed.get("sealed") is not True or sealed.get("predictionOpened") is not False:
        raise SystemExit("Sealed prediction-blind manifest required")
    if sealed.get("manifestSha256") != sealed_digest(sealed):
        raise SystemExit("Sealed manifest digest mismatch")
    documents = make_documents(root, sealed)
    if len(documents) != sealed.get("documentCount"):
        raise SystemExit("Replay and sealed document counts differ")
    before = evaluate_variant(documents, "baseline")
    after = evaluate_variant(documents, "phase11_10")
    improvements = regressions = 0
    for document in documents:
        for name in FIELD_ORDER:
            expected = value(document["groundTruth"].get(name))
            before_exact = value(document["baseline"].get(name)) == expected
            after_exact = value(document["phase11_10"].get(name)) == expected
            improvements += int(not before_exact and after_exact)
            regressions += int(before_exact and not after_exact)
    schema_errors = sum(
        1
        for document in documents
        for name in FIELD_ORDER
        if not isinstance(document["phase11_10"].get(name), dict)
    )
    all_manual = all(
        field.get("status") != "accepted"
        for document in documents
        for field in document["phase11_10"].values()
        if isinstance(field, dict)
    )
    protected_regressions = 0
    protected_keys = (
        "value", "asciiValue", "confidence", "errorSignals", "evidence",
        "selectionMode", "validation",
    )
    for document in documents:
        baseline_fields = document["baseline"]
        candidate_fields = document["phase11_10"]
        for name in PROTECTED_FIELDS:
            protected_regressions += int(
                {key: baseline_fields.get(name, {}).get(key) for key in protected_keys}
                != {key: candidate_fields.get(name, {}).get(key) for key in protected_keys}
            )
    secondary_path = root / "phase11_10_v2_private" / "secondary_predictions_private.json"
    secondary = (
        json.loads(secondary_path.read_text(encoding="utf-8"))
        if secondary_path.is_file()
        else {}
    )
    report = {
        "schemaVersion": "ocr-ho-v2-014-evaluation/2.0.0",
        "candidateVersion": "11.10.0",
        "baselineVersion": "11.5",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": len(documents),
        "targetFields": list(TARGET_FIELDS),
        "protectedFields": list(PROTECTED_FIELDS),
        "policyId": "phase11.10-v2-line-aware-name-address",
        "containsRawPII": False,
        "predictionOpened": False,
        "sealedManifestSha256": sealed["manifestSha256"],
        "sealedManifestFileSha256": file_sha256(sealed_path),
        "metrics": {"baseline_phase11_5": before, "ocr_ho_v2_014": after},
        "errorAnalyzer": {
            "classes": CLASS_NAMES,
            "baseline11_5": class_report(documents, "baseline"),
            "candidate11_10": class_report(documents, "phase11_10"),
        },
        "gates": gates(
            before,
            after,
            improvements=improvements,
            regressions=regressions,
            schema_errors=schema_errors,
            all_manual_review=all_manual,
            protected_regressions=protected_regressions,
        ),
        "exactImprovementCount": improvements,
        "exactRegressionCount": regressions,
        "schemaErrorCount": schema_errors,
        "protectedFieldRegressionCount": protected_regressions,
        "warningCounts": secondary.get("warningCounts", {}),
        "replay": {
            "recognizers": [
                "paddle_ppocrv5",
                "easyocr_vi",
                "vietocr_vgg_seq2seq",
                "vietocr_vgg_transformer",
            ],
            "lineMapping": "sealed_ground_truth_line_ids",
            "resultArtifact": "PHASE11_10_V2_RESULTS.json",
        },
    }
    output = (
        args.output
        or root / "output" / "phase11" / "reports"
        / "CCCD_OCR_HO_V2_014_DEVELOPMENT_COMPARISON.json"
    ).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["gates"], ensure_ascii=False))
    return 0


def sealed_digest(payload: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "manifestSha256"}
    encoded = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

if __name__ == "__main__":
    raise SystemExit(main())
