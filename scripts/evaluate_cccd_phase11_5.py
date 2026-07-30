#!/usr/bin/env python3
"""Evaluate Phase 11.5 on reviewed CCCD without exporting raw PII."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "ocr_lab" / "api"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from phase11_5_cccd import FIELD_ORDER, ascii_text, base_key  # noqa: E402

from hcns_agent.application.ocr_metrics import (  # noqa: E402
    evaluate_text_pairs,
    normalize_for_evaluation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def value(field: Any, key: str = "value") -> str:
    if isinstance(field, dict):
        field = field.get(key)
    return normalize_for_evaluation(str(field or ""))


def is_subsequence(shorter: str, longer: str) -> bool:
    iterator = iter(longer)
    return all(character in iterator for character in shorter)


def error_class(expected: str, predicted: str, field: dict[str, Any]) -> str:
    if not predicted:
        return "not_found"
    if normalize_for_evaluation(expected) == normalize_for_evaluation(predicted):
        return "exact"
    expected_base = base_key(expected)
    predicted_base = base_key(predicted)
    if expected_base == predicted_base:
        return "diacritics_only"
    if any(signal == "label_contamination" for signal in field.get("errorSignals", [])):
        return "label_contamination"
    if expected_base.replace(" ", "") == predicted_base.replace(" ", ""):
        return "line_merge_or_split"
    compact_expected = expected_base.replace(" ", "")
    compact_predicted = predicted_base.replace(" ", "")
    if len(compact_predicted) < len(compact_expected) and is_subsequence(
        compact_predicted, compact_expected
    ):
        return "character_omission"
    if field.get("selectionMode") == "single_candidate" and (
        len(compact_predicted) < len(compact_expected) * 0.55
        or len(compact_predicted) > len(compact_expected) * 1.8
    ):
        return "region_mismatch"
    if field.get("validation", {}).get("rule") == "known_enum":
        return "enum_confusion"
    if field.get("validation", {}).get("rule") in {
        "valid_calendar_date",
        "expiry_after_birth",
    }:
        expected_parts = expected.replace("-", "/").replace(".", "/").split("/")
        predicted_parts = predicted.replace("-", "/").replace(".", "/").split("/")
        if len(expected_parts) == len(predicted_parts) == 3:
            return (
                "year_mismatch"
                if expected_parts[-1] != predicted_parts[-1]
                else "date_component_mismatch"
            )
    return "character_substitution"


def candidate_contains_expected(field: dict[str, Any], expected: str) -> bool:
    expected_key = base_key(expected)
    if not expected_key:
        return False
    candidates = (field.get("evidence") or {}).get("candidates", [])
    return any(
        expected_key in base_key(candidate.get("rawValue") or candidate.get("value"))
        for candidate in candidates
    )


def evaluate_variant(
    documents: list[dict[str, Any]],
    variant: str,
) -> dict[str, Any]:
    pairs: list[tuple[str, str]] = []
    base_pairs: list[tuple[str, str]] = []
    errors: Counter[str] = Counter()
    per_field: dict[str, Counter[str]] = defaultdict(Counter)
    candidate_profile: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    accepted = accepted_exact = present = region_correct = 0
    sensitive_false = 0
    sensitive = {"identityNumber", "dateOfBirth", "sex", "dateOfExpiry"}
    for document in documents:
        ground_truth = document["groundTruth"]
        fields = document[variant]
        for field_name in FIELD_ORDER:
            expected = value(ground_truth.get(field_name))
            if not expected:
                continue
            field = fields.get(field_name) or {}
            predicted = value(field)
            predicted_ascii = value(field, "asciiValue") or ascii_text(predicted)
            pairs.append((expected, predicted))
            base_pairs.append((ascii_text(expected), predicted_ascii))
            category = error_class(expected, predicted, field)
            errors[category] += 1
            per_field[field_name]["evaluated"] += 1
            per_field[field_name]["exact"] += int(category == "exact")
            per_field[field_name]["asciiExact"] += int(
                base_key(expected) == base_key(predicted_ascii)
            )
            per_field[field_name]["omission"] += int(category == "character_omission")
            is_present = bool(predicted)
            present += int(is_present)
            per_field[field_name]["present"] += int(is_present)
            region_hit = (
                candidate_contains_expected(field, expected)
                if variant == "phase11_5"
                else category
                not in {
                    "region_mismatch",
                    "label_contamination",
                    "not_found",
                }
            )
            region_correct += int(region_hit)
            per_field[field_name]["regionCorrect"] += int(region_hit)
            if variant == "phase11_5":
                candidates = (field.get("evidence") or {}).get("candidates", [])
                strict_oracle = any(
                    value(candidate) == expected for candidate in candidates
                )
                ascii_oracle = any(
                    base_key(value(candidate)) == base_key(expected)
                    for candidate in candidates
                )
                per_field[field_name]["candidateStrictOracle"] += int(strict_oracle)
                per_field[field_name]["candidateAsciiOracle"] += int(ascii_oracle)
                for candidate in candidates:
                    profile = str(candidate.get("profile") or "unknown")
                    candidate_profile[field_name][profile]["evaluated"] += 1
                    candidate_profile[field_name][profile]["strict"] += int(
                        value(candidate) == expected
                    )
                    candidate_profile[field_name][profile]["ascii"] += int(
                        base_key(value(candidate)) == base_key(expected)
                    )
            is_accepted = field.get("status") == "accepted"
            is_exact = category == "exact"
            accepted += int(is_accepted)
            accepted_exact += int(is_accepted and is_exact)
            per_field[field_name]["accepted"] += int(is_accepted)
            per_field[field_name]["acceptedExact"] += int(is_accepted and is_exact)
            sensitive_false += int(field_name in sensitive and is_accepted and not is_exact)
    strict_metrics = evaluate_text_pairs(pairs)
    base_metrics = evaluate_text_pairs(base_pairs)
    evaluated = len(pairs)
    per_field_out = {
        name: {
            "evaluatedCount": row["evaluated"],
            "exactMatch": round(row["exact"] / max(1, row["evaluated"]), 6),
            "asciiExactMatch": round(row["asciiExact"] / max(1, row["evaluated"]), 6),
            "characterOmissionRate": round(row["omission"] / max(1, row["evaluated"]), 6),
            "fieldPresence": round(row["present"] / max(1, row["evaluated"]), 6),
            "acceptedPrecision": round(
                row["acceptedExact"] / max(1, row["accepted"]),
                6,
            ),
            "acceptedCoverage": round(
                row["accepted"] / max(1, row["evaluated"]),
                6,
            ),
            "regionSelectionAccuracy": round(
                row["regionCorrect"] / max(1, row["evaluated"]),
                6,
            ),
            "candidateStrictOracle": round(
                row["candidateStrictOracle"] / max(1, row["evaluated"]),
                6,
            ),
            "candidateAsciiOracle": round(
                row["candidateAsciiOracle"] / max(1, row["evaluated"]),
                6,
            ),
            "candidateProfiles": {
                profile: {
                    "strictExactCount": profile_row["strict"],
                    "asciiExactCount": profile_row["ascii"],
                    "candidateCount": profile_row["evaluated"],
                }
                for profile, profile_row in sorted(
                    candidate_profile[name].items()
                )
            },
        }
        for name, row in per_field.items()
    }
    return {
        "evaluatedFieldCount": evaluated,
        "strictFieldExactMatch": strict_metrics.strict_exact_rate,
        "asciiFieldExactMatch": base_metrics.strict_exact_rate,
        "cer": strict_metrics.character_error_rate,
        "baseCer": base_metrics.character_error_rate,
        "der": strict_metrics.diacritic_error_rate,
        "characterOmissionRate": round(errors["character_omission"] / max(1, evaluated), 6),
        "fieldPresence": round(present / max(1, evaluated), 6),
        "acceptedPrecision": round(accepted_exact / max(1, accepted), 6),
        "acceptedCoverage": round(accepted / max(1, evaluated), 6),
        "regionSelectionAccuracy": round(region_correct / max(1, evaluated), 6),
        "sensitiveFieldFalseAcceptanceCount": sensitive_false,
        "meanDurationMs": round(
            sum(float(document["durations"].get(variant) or 0.0) for document in documents)
            / max(1, len(documents)),
            3,
        ),
        "errorClasses": dict(sorted(errors.items())),
        "perField": per_field_out,
    }


def load_documents(data_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    documents = []
    sessions = data_root / "user_uploads" / "sessions"
    for record in manifest.get("records", []):
        session = sessions / str(record.get("sessionId", ""))
        ground_truth_path = session / "phase10" / "ground_truth.json"
        result_path = session / "result.json"
        before_path = session / "phase11" / "history" / "identity_card_phase11_4.json"
        if not (ground_truth_path.is_file() and result_path.is_file() and before_path.is_file()):
            continue
        ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
        assertions = ground_truth.get("verificationAssertions", {})
        if not (
            assertions.get("comparedWithImage") is True and assertions.get("allTextChecked") is True
        ):
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("phase11_5", {}).get("status") != "COMPLETE":
            continue
        documents.append(
            {
                "groundTruth": ground_truth.get("identityFields", {}),
                "phase11_4": json.loads(before_path.read_text(encoding="utf-8")).get("fields", {}),
                "phase11_5": (result.get("phase11", {}).get("identityCard", {}).get("fields", {})),
                "durations": {
                    "phase11_4": (result.get("phase11_4", {}).get("durationMs") or 0.0),
                    "phase11_5": (result.get("phase11_5", {}).get("durationMs") or 0.0),
                },
            }
        )
    return documents


def gate(
    before: dict[str, Any],
    after: dict[str, Any],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    regressions = 0
    regressions_by_field: Counter[str] = Counter()
    for document in documents:
        for field_name in FIELD_ORDER:
            expected = value(document["groundTruth"].get(field_name))
            if not expected:
                continue
            before_value = value(document["phase11_4"].get(field_name))
            after_value = value(document["phase11_5"].get(field_name))
            regressed = before_value == expected and after_value != expected
            regressions += int(regressed)
            regressions_by_field[field_name] += int(regressed)
    full_name_ascii = after["perField"].get("fullName", {}).get("asciiExactMatch", 0.0)
    address_rows = [
        after["perField"].get(name, {}).get("asciiExactMatch", 0.0)
        for name in ("placeOfOrigin", "placeOfResidence")
    ]
    address_ascii = sum(address_rows) / len(address_rows)
    omission_reduction = (
        (before["characterOmissionRate"] - after["characterOmissionRate"])
        / before["characterOmissionRate"]
        if before["characterOmissionRate"]
        else 0.0
    )
    checks = {
        "acceptedPrecision": after["acceptedPrecision"] == 1.0,
        "noExactRegression": regressions == 0,
        "fullNameAsciiExactMatch": full_name_ascii >= 0.90,
        "addressAsciiExactMatch": address_ascii >= 0.85,
        "characterOmissionReduction": omission_reduction >= 0.50,
        "fieldPresence": after["fieldPresence"] >= 0.95,
        "noSensitiveFalseAcceptance": (after["sensitiveFieldFalseAcceptanceCount"] == 0),
    }
    return {
        "status": "PROMOTION_ELIGIBLE" if all(checks.values()) else "SHADOW_REVIEW_ONLY",
        "checks": checks,
        "exactRegressionCount": regressions,
        "exactRegressionByField": dict(sorted(regressions_by_field.items())),
        "fullNameAsciiExactMatch": full_name_ascii,
        "addressAsciiExactMatch": round(address_ascii, 6),
        "characterOmissionReduction": round(omission_reduction, 6),
    }


def markdown(report: dict[str, Any]) -> str:
    before = report["metrics"]["phase11_4"]
    after = report["metrics"]["phase11_5"]

    def metric_row(label: str, key: str) -> str:
        return f"| {label} | {before[key]:.2%} | {after[key]:.2%} |"

    lines = [
        "# Phase 11.5 CCCD Development Evaluation",
        "",
        f"- Documents: {report['documentCount']}",
        f"- Decision: **{report['promotionGate']['status']}**",
        "- Dataset role: development/regression; not a final held-out promotion set.",
        "",
        "| Metric | Phase 11.4 | Phase 11.5 |",
        "|---|---:|---:|",
        metric_row("Strict Field Exact Match", "strictFieldExactMatch"),
        metric_row("ASCII Field Exact Match", "asciiFieldExactMatch"),
        metric_row("CER", "cer"),
        metric_row("Base CER", "baseCer"),
        metric_row("DER", "der"),
        metric_row("Character Omission Rate", "characterOmissionRate"),
        metric_row("Field Presence", "fieldPresence"),
        metric_row("Accepted Precision", "acceptedPrecision"),
        metric_row("Accepted Coverage", "acceptedCoverage"),
        metric_row("Region Selection Accuracy", "regionSelectionAccuracy"),
        "",
        (
            "- Mean OCR duration: "
            f"Phase 11.4 {before['meanDurationMs']:.1f} ms/document; "
            f"Phase 11.5 {after['meanDurationMs']:.1f} ms/document."
        ),
        "",
        "No raw OCR text, Ground Truth value, or PII is included in this report.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report_dir = args.data_root / "output" / "phase11" / "reports"
    json_path = report_dir / "CCCD_PHASE11_5_DEVELOPMENT_EVALUATION.json"
    md_path = report_dir / "CCCD_PHASE11_5_DEVELOPMENT_EVALUATION.md"
    if json_path.is_file() and not args.overwrite:
        raise FileExistsError("Report exists; pass --overwrite")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    documents = load_documents(args.data_root, manifest)
    before = evaluate_variant(documents, "phase11_4")
    after = evaluate_variant(documents, "phase11_5")
    report = {
        "schemaVersion": "phase11.5-evaluation/1.0.0",
        "containsRawPII": False,
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": len(documents),
        "metrics": {"phase11_4": before, "phase11_5": after},
        "promotionGate": gate(before, after, documents),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["promotionGate"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
