#!/usr/bin/env python3
"""Evaluate OCR-HO-V2-011 on the private 15-document development replay."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from jsonschema import ValidationError, validate
except ModuleNotFoundError:  # pragma: no cover - minimal OCR runtime fallback
    ValidationError = ValueError  # type: ignore[assignment,misc]

    def validate(instance: dict[str, Any], _schema: dict[str, Any]) -> None:
        if instance.get("schemaVersion") != "11.6.0":
            raise ValidationError("schema version")
        if instance.get("documentType") != "VIETNAM_CITIZEN_ID_FRONT":
            raise ValidationError("document type")
        if instance.get("policyMode") != "SHADOW_REVIEW_ONLY":
            raise ValidationError("policy mode")
        if set(instance.get("fields", {})) != set(FIELD_ORDER):
            raise ValidationError("field keys")


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "ocr_lab" / "api"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from evaluate_cccd_phase11_5 import evaluate_variant, value  # noqa: E402
from phase11_5_cccd import FIELD_ORDER  # noqa: E402
from phase11_9_cccd_v2 import (  # noqa: E402
    CANDIDATE_VERSION,
    POLICY_ID,
    PROTECTED_FIELDS,
    TARGET_FIELDS,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def session_root(data_root: Path) -> Path:
    for candidate in (
        data_root / "user_uploads-sessions",
        data_root / "user_uploads" / "sessions",
    ):
        if candidate.is_dir():
            return candidate
    raise RuntimeError("No development session root found")


def load_documents(
    data_root: Path,
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, int, Counter[str]]:
    documents: list[dict[str, Any]] = []
    rotations = skipped = 0
    recognizers: Counter[str] = Counter()
    sessions = session_root(data_root)
    for record in manifest.get("records", []):
        session = sessions / str(record.get("sessionId", ""))
        paths = {
            "groundTruth": session / "phase10" / "ground_truth.json",
            "baseline": session / "phase11_5" / "identity_card.json",
            "candidate": session / "phase11_9_v2" / "field_consensus.json",
            "result": session / "result.json",
        }
        if not all(path.is_file() for path in paths.values()):
            skipped += 1
            continue
        if int(record.get("selectedRotationDegrees") or 0) != 0:
            rotations += 1
            continue
        ground_truth = json.loads(paths["groundTruth"].read_text(encoding="utf-8"))
        assertions = ground_truth.get("verificationAssertions", {})
        if not (
            assertions.get("comparedWithImage") is True
            and assertions.get("allTextChecked") is True
        ):
            skipped += 1
            continue
        baseline = json.loads(paths["baseline"].read_text(encoding="utf-8"))
        candidate = json.loads(paths["candidate"].read_text(encoding="utf-8"))
        baseline_fields = baseline.get("fields") or {}
        candidate_card = candidate.get("identityCard") or {}
        candidate_fields = candidate_card.get("fields") or {}
        if set(baseline_fields) != set(FIELD_ORDER) or set(candidate_fields) != set(FIELD_ORDER):
            skipped += 1
            continue
        result = json.loads(paths["result"].read_text(encoding="utf-8"))
        phase = result.get("phase11_9_v2") or {}
        recognizers.update(str(item) for item in phase.get("recognizers") or [])
        documents.append(
            {
                "documentIndex": int(record.get("documentIndex", 0)),
                "groundTruth": ground_truth.get("identityFields", {}),
                "phase11_5": baseline_fields,
                "ocr_ho_v2_011": candidate_fields,
                "candidateCard": candidate_card,
                "durations": {
                    "phase11_5": result.get("phase11_5", {}).get("durationMs") or 0.0,
                    "ocr_ho_v2_011": phase.get("durationMs") or 0.0,
                },
            }
        )
    return documents, rotations, skipped, recognizers


def exact_delta(
    documents: list[dict[str, Any]],
) -> tuple[int, int, dict[str, int], dict[str, int]]:
    improvements = regressions = 0
    improved: Counter[str] = Counter()
    regressed: Counter[str] = Counter()
    for document in documents:
        for field_name in FIELD_ORDER:
            expected = value(document["groundTruth"].get(field_name))
            if not expected:
                continue
            before = value(document["phase11_5"].get(field_name)) == expected
            after = value(document["ocr_ho_v2_011"].get(field_name)) == expected
            if after and not before:
                improvements += 1
                improved[field_name] += 1
            elif before and not after:
                regressions += 1
                regressed[field_name] += 1
    return (
        improvements,
        regressions,
        dict(sorted(improved.items())),
        dict(sorted(regressed.items())),
    )


def schema_error_count(documents: list[dict[str, Any]]) -> int:
    schema_path = REPO_ROOT / "schemas" / "vietnam_identity_card_phase11_6.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = 0
    for document in documents:
        try:
            validate(document["candidateCard"], schema)
        except (ValidationError, TypeError):
            errors += 1
    return errors


def build_gate(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    documents: list[dict[str, Any]],
    schema_errors: int,
) -> dict[str, Any]:
    improvements, regressions, improved, regressed = exact_delta(documents)
    manual_review = all(
        field.get("status") != "accepted"
        for document in documents
        for field in document["ocr_ho_v2_011"].values()
    )
    checks = {
        "strictExactMatchNotWorse": (
            candidate["strictFieldExactMatch"] >= baseline["strictFieldExactMatch"]
        ),
        "asciiExactMatchNotWorse": (
            candidate["asciiFieldExactMatch"] >= baseline["asciiFieldExactMatch"]
        ),
        "cerNotWorse": candidate["cer"] <= baseline["cer"],
        "derNotWorse": candidate["der"] <= baseline["der"],
        "fieldPresenceNotWorse": candidate["fieldPresence"] >= baseline["fieldPresence"],
        "noExactRegression": regressions == 0,
        "schemaErrorsZero": schema_errors == 0,
        "manualReviewPolicy": manual_review,
        "hasExactImprovement": improvements >= 1,
    }
    return {
        "status": "DEVELOPMENT_PASS" if all(checks.values()) else "DEVELOPMENT_FAIL",
        "productionPromotionAllowed": False,
        "checks": checks,
        "exactImprovementCount": improvements,
        "exactRegressionCount": regressions,
        "exactImprovementByField": improved,
        "exactRegressionByField": regressed,
        "schemaErrorCount": schema_errors,
        "manualReviewFieldCount": sum(
            field.get("status") != "accepted"
            for document in documents
            for field in document["ocr_ho_v2_011"].values()
        ),
    }


def markdown(report: dict[str, Any]) -> str:
    baseline = report["metrics"]["baseline_phase11_5"]
    candidate = report["metrics"]["ocr_ho_v2_011"]
    gate = report["promotionGate"]

    def row(label: str, key: str) -> str:
        return f"| {label} | {baseline[key]:.2%} | {candidate[key]:.2%} |"

    return "\n".join(
        [
            "# OCR-HO-V2-011 Development Comparison",
            "",
            f"- Development documents in scope: {report['documentCount']}",
            f"- Candidate: OCR-HO-V2 v{report['candidateVersion']} (`{report['policyId']}`)",
            f"- Target fields: {', '.join(report['targetFields'])}",
            f"- Recognizer profiles replayed: {', '.join(report['recognizerProfiles'])}",
            f"- Decision: **{gate['status']}**",
            "- Production promotion: **not allowed**; development shadow comparison only.",
            "- Ground Truth was scoring-only; candidate selection used deterministic "
            "OCR ROI evidence.",
            "",
            "| Metric | Baseline Phase 11.5 | OCR-HO-V2-011 |",
            "|---|---:|---:|",
            row("Strict Field Exact Match", "strictFieldExactMatch"),
            row("ASCII Field Exact Match", "asciiFieldExactMatch"),
            row("CER", "cer"),
            row("Base CER", "baseCer"),
            row("DER", "der"),
            row("Field Presence", "fieldPresence"),
            row("Accepted Precision", "acceptedPrecision"),
            "",
            (
                f"- Exact improvements/regressions: {gate['exactImprovementCount']}/"
                f"{gate['exactRegressionCount']}."
            ),
            (
                f"- Schema errors: {gate['schemaErrorCount']}; manual-review fields: "
                f"{gate['manualReviewFieldCount']}."
            ),
            "- No raw OCR text, Ground Truth value, or PII is included in this report.",
            "",
        ]
    )


def main() -> int:
    args = parse_args()
    report_dir = args.data_root / "output" / "phase11" / "reports"
    json_path = report_dir / "CCCD_OCR_HO_V2_011_DEVELOPMENT_COMPARISON.json"
    md_path = report_dir / "CCCD_OCR_HO_V2_011_DEVELOPMENT_COMPARISON.md"
    if (json_path.is_file() or md_path.is_file()) and not args.overwrite:
        raise FileExistsError("Report exists; pass --overwrite")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    documents, rotations, skipped, recognizers = load_documents(args.data_root, manifest)
    if not documents:
        raise RuntimeError("No eligible development documents found")
    baseline = evaluate_variant(documents, "phase11_5")
    candidate = evaluate_variant(documents, "ocr_ho_v2_011")
    report = {
        "schemaVersion": "ocr-ho-v2-011-evaluation/1.0.0",
        "containsRawPII": False,
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "candidateVersion": CANDIDATE_VERSION,
        "policyId": POLICY_ID,
        "targetFields": list(TARGET_FIELDS),
        "protectedFields": list(PROTECTED_FIELDS),
        "recognizerProfiles": sorted(recognizers),
        "documentCount": len(documents),
        "outOfScopeRotationDocumentCount": rotations,
        "skippedDocumentCount": skipped,
        "metrics": {"baseline_phase11_5": baseline, "ocr_ho_v2_011": candidate},
        "promotionGate": build_gate(baseline, candidate, documents, schema_error_count(documents)),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["promotionGate"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
