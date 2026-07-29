#!/usr/bin/env python3
"""Analyze Phase 14.8 without retaining private text in the output.

The 309-line corpus is the development corpus. The 149 confirmed Phase 14.7
lines are diagnostic held-out evidence only and are never used to tune a
threshold or replace the Seq2Seq primary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hcns_agent.application.ocr_metrics import (
    METRIC_SPEC_VERSION,
    normalize_for_agreement,
    normalize_for_evaluation,
    strip_vietnamese_diacritics,
)
from hcns_agent.application.phase14_7_evaluation import metric_payload
from hcns_agent.application.phase14_7_protocol import atomic_write_json
from hcns_agent.application.recognition_policy import (
    PHASE14_8_TRANSFORMER_VERIFIER_POLICY,
)

PRIMARY = "vietocr_vgg_seq2seq"
TRANSFORMER = "vietocr_vgg_transformer"


@dataclass(frozen=True, slots=True)
class Record:
    document_key: str
    reference: str
    primary: str
    transformer: str
    primary_confidence: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path.name}")
    return value


def safe_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def classify_error(reference: str, prediction: str) -> str:
    if reference == prediction:
        return "exact"
    if not prediction:
        return "empty"
    if strip_vietnamese_diacritics(
        reference
    ) == strip_vietnamese_diacritics(prediction):
        return "diacritic_only"
    if len(prediction) < len(reference):
        return "missing_or_substituted_characters"
    if len(prediction) > len(reference):
        return "extra_or_substituted_characters"
    return "substitution_or_spacing"


def development_records(
    queue: dict[str, Any],
    reviews: dict[str, Any],
    predictions: dict[str, Any],
) -> list[Record]:
    if queue.get("queueDigest") != predictions.get("queueDigest"):
        raise ValueError("Development queue and predictions differ")
    if predictions.get("predictionsHiddenDuringReview") is not True:
        raise ValueError("Development predictions were not blinded")
    prediction_cases = {
        str(case["caseId"]): case for case in predictions.get("cases", [])
    }
    review_cases = reviews.get("reviews")
    if not isinstance(review_cases, dict):
        raise ValueError("Development Ground Truth review store is invalid")
    if len(review_cases) != int(queue.get("lineCount", -1)):
        raise ValueError("Development Ground Truth is not fully reviewed")
    records: list[Record] = []
    for case in queue.get("cases", []):
        case_id = str(case.get("caseId", ""))
        prediction = prediction_cases.get(case_id)
        review = review_cases.get(case_id)
        if not isinstance(review, dict):
            raise ValueError("A development Ground Truth review is missing")
        if (
            review.get("comparedWithCrop") is not True
            or review.get("allTextChecked") is not True
        ):
            raise ValueError("Development Ground Truth evidence is incomplete")
        reference = normalize_for_evaluation(
            str(review.get("groundTruth", ""))
        )
        if not case_id or prediction is None or not reference:
            raise ValueError("Development case is incomplete")
        profiles = prediction.get("predictions", {})
        if PRIMARY not in profiles or TRANSFORMER not in profiles:
            raise ValueError("Development case is missing a locked recognizer")
        primary = profiles[PRIMARY]
        records.append(
            Record(
                document_key=str(case.get("documentKey", "")),
                reference=reference,
                primary=normalize_for_evaluation(str(primary.get("text", ""))),
                transformer=normalize_for_evaluation(
                    str(profiles[TRANSFORMER].get("text", ""))
                ),
                primary_confidence=safe_confidence(primary.get("confidence")),
            )
        )
    if len(records) != int(queue.get("lineCount", -1)):
        raise ValueError("Development line count mismatch")
    if len({record.document_key for record in records}) != int(
        queue.get("documentCount", -1)
    ):
        raise ValueError("Development document count mismatch")
    return records


def heldout_records(
    ground_truth: dict[str, Any],
    predictions: dict[str, Any],
) -> tuple[list[Record], int]:
    if (
        ground_truth.get("groundTruthStatus")
        != "USER_CONFIRMED_HELD_OUT_GROUND_TRUTH"
        or ground_truth.get("predictionsVisibleDuringReview") is not False
    ):
        raise ValueError("Held-out Ground Truth evidence is incomplete")
    if ground_truth.get("queueDigest") != predictions.get("queueDigest"):
        raise ValueError("Held-out Ground Truth and predictions differ")
    prediction_cases = {
        str(case["caseId"]): case for case in predictions.get("cases", [])
    }
    records: list[Record] = []
    skipped = 0
    for case in ground_truth.get("cases", []):
        status = str(case.get("status", ""))
        if status == "SKIPPED":
            skipped += 1
            continue
        if status != "CONFIRMED":
            raise ValueError("Held-out Ground Truth review is not complete")
        case_id = str(case.get("caseId", ""))
        prediction = prediction_cases.get(case_id)
        reference = normalize_for_evaluation(
            str(case.get("confirmedTranscription", ""))
        )
        if prediction is None or not reference:
            raise ValueError("Held-out case is incomplete")
        profiles = prediction.get("predictions", {})
        if PRIMARY not in profiles or TRANSFORMER not in profiles:
            raise ValueError("Held-out case is missing a locked recognizer")
        primary = profiles[PRIMARY]
        records.append(
            Record(
                document_key=str(case.get("documentId", "")),
                reference=reference,
                primary=normalize_for_evaluation(str(primary.get("text", ""))),
                transformer=normalize_for_evaluation(
                    str(profiles[TRANSFORMER].get("text", ""))
                ),
                primary_confidence=safe_confidence(primary.get("confidence")),
            )
        )
    return records, skipped


def analyze_corpus(records: list[Record], *, skipped_count: int = 0) -> dict[str, Any]:
    if not records:
        raise ValueError("Cannot analyze an empty corpus")
    primary_pairs = [(record.reference, record.primary) for record in records]
    transformer_pairs = [
        (record.reference, record.transformer) for record in records
    ]
    strict_agreements = [
        record
        for record in records
        if record.primary
        and normalize_for_evaluation(record.primary)
        == normalize_for_evaluation(record.transformer)
    ]
    casefold_agreements = [
        record
        for record in records
        if record.primary
        and normalize_for_agreement(record.primary)
        == normalize_for_agreement(record.transformer)
    ]
    strict_agreement_exact = sum(
        record.primary == record.reference for record in strict_agreements
    )
    primary_errors = [
        record for record in records if record.primary != record.reference
    ]
    transformer_recoveries = sum(
        record.primary != record.reference
        and record.transformer == record.reference
        for record in records
    )
    transformer_loss_if_selected = sum(
        record.primary == record.reference
        and record.transformer != record.reference
        for record in records
    )
    oracle_exact = sum(
        record.reference in {record.primary, record.transformer}
        for record in records
    )
    taxonomy = Counter(
        classify_error(record.reference, record.primary)
        for record in primary_errors
    )
    decisions = [
        PHASE14_8_TRANSFORMER_VERIFIER_POLICY.decide(
            primary_text=record.primary,
            primary_confidence=record.primary_confidence,
            verifier_text=record.transformer,
        )
        for record in records
    ]
    if any(
        decision.selected_text != record.primary
        for record, decision in zip(records, decisions, strict=True)
    ):
        raise AssertionError("Phase 14.8 policy replaced primary text")
    verified_count = sum(decision.status == "verified" for decision in decisions)
    needs_review_count = len(decisions) - verified_count
    return {
        "documentCount": len({record.document_key for record in records}),
        "evaluatedLineCount": len(records),
        "skippedLineCount": skipped_count,
        "profiles": {
            PRIMARY: metric_payload(primary_pairs),
            TRANSFORMER: metric_payload(transformer_pairs),
        },
        "primaryErrorAnalysis": {
            "errorCount": len(primary_errors),
            "categoryCounts": dict(sorted(taxonomy.items())),
            "transformerExactRecoveryCount": transformer_recoveries,
            "transformerLossIfBlindlySelectedCount": (
                transformer_loss_if_selected
            ),
            "twoRecognizerOracleExactCount": oracle_exact,
            "twoRecognizerOracleExactRate": round(
                oracle_exact / len(records),
                6,
            ),
        },
        "verifierAgreement": {
            "strictAgreementCount": len(strict_agreements),
            "strictAgreementCoverage": round(
                len(strict_agreements) / len(records),
                6,
            ),
            "strictAgreementExactCount": strict_agreement_exact,
            "strictAgreementPrecision": round(
                strict_agreement_exact / max(1, len(strict_agreements)),
                6,
            ),
            "casefoldAgreementCount": len(casefold_agreements),
            "casefoldAgreementCoverage": round(
                len(casefold_agreements) / len(records),
                6,
            ),
        },
        "policyReplay": {
            "selectedProfile": PRIMARY,
            "verifierProfile": TRANSFORMER,
            "paddleEligibleForSelection": False,
            "selectedTextChangedCount": 0,
            "verifiedLineCount": verified_count,
            "needsReviewLineCount": needs_review_count,
            "verifiedCoverage": round(verified_count / len(records), 6),
            "verifiedPrecision": round(
                strict_agreement_exact / max(1, verified_count),
                6,
            ),
            "metrics": metric_payload(primary_pairs),
        },
    }


def build_analysis(
    *,
    development: list[Record],
    heldout: list[Record],
    heldout_skipped: int,
    source_digests: dict[str, str],
) -> dict[str, Any]:
    policy = PHASE14_8_TRANSFORMER_VERIFIER_POLICY.manifest()
    return {
        "schemaVersion": "phase14.8-verifier-analysis/1.0.0",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "containsRealPII": False,
        "metricSpecVersion": METRIC_SPEC_VERSION,
        "sourceDigests": source_digests,
        "policy": policy,
        "developmentCorpus": analyze_corpus(development),
        "heldOutDiagnostic": analyze_corpus(
            heldout,
            skipped_count=heldout_skipped,
        ),
        "decision": {
            "primary": PRIMARY,
            "verifier": TRANSFORMER,
            "paddleRole": "DETECTOR_GEOMETRY_AND_AUDIT_EVIDENCE_ONLY",
            "paddleFallbackEnabled": False,
            "autoReplaceSelectedText": False,
            "policyMode": "SHADOW_REVIEW_ONLY",
            "heldOutUsedForThresholdTuning": False,
            "promotion": "NOT_PRODUCTION_READY",
        },
    }


def percentage(value: float) -> str:
    return f"{value * 100:.2f}%"


def build_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 14.8 — Seq2Seq primary + Transformer verifier",
        "",
        "> Aggregate-only report. Không chứa Ground Truth, prediction, "
        "document ID hoặc PII theo dòng.",
        "",
        "## Policy cố định",
        "",
        "- Primary: `vietocr_vgg_seq2seq`",
        "- Verifier: `vietocr_vgg_transformer`",
        "- Paddle: chỉ detector/geometry/evidence; không được chọn làm text",
        "- Bất đồng: giữ Seq2Seq và chuyển `needs_review`",
        "- Đồng thuận nghiêm ngặt: chỉ đánh dấu `verified`, không tự thay text",
        "- Mode: `SHADOW_REVIEW_ONLY`",
        "",
    ]
    for title, key in (
        ("Development 309 dòng", "developmentCorpus"),
        ("Held-out diagnostic 149 dòng", "heldOutDiagnostic"),
    ):
        corpus = payload[key]
        primary = corpus["profiles"][PRIMARY]
        transformer = corpus["profiles"][TRANSFORMER]
        agreement = corpus["verifierAgreement"]
        errors = corpus["primaryErrorAnalysis"]
        lines.extend(
            [
                f"## {title}",
                "",
                f"- Documents: **{corpus['documentCount']}**",
                f"- Evaluated lines: **{corpus['evaluatedLineCount']}**",
                f"- Primary errors: **{errors['errorCount']}**",
                f"- Transformer exact recoveries: "
                f"**{errors['transformerExactRecoveryCount']}**",
                f"- Transformer losses if blindly selected: "
                f"**{errors['transformerLossIfBlindlySelectedCount']}**",
                f"- Strict agreement coverage: "
                f"**{percentage(agreement['strictAgreementCoverage'])}**",
                f"- Strict agreement precision: "
                f"**{percentage(agreement['strictAgreementPrecision'])}**",
                "",
                "| Profile | Exact Match | CER | WER | DER |",
                "|---|---:|---:|---:|---:|",
                f"| Seq2Seq | {percentage(primary['exactMatchRate'])} | "
                f"{percentage(primary['cer'])} | "
                f"{percentage(primary['wer'])} | "
                f"{percentage(primary['der'])} |",
                f"| Transformer | "
                f"{percentage(transformer['exactMatchRate'])} | "
                f"{percentage(transformer['cer'])} | "
                f"{percentage(transformer['wer'])} | "
                f"{percentage(transformer['der'])} |",
                "",
            ]
        )
    lines.extend(
        [
            "## Kết luận",
            "",
            "Seq2Seq vẫn là text chính. Transformer chỉ bổ sung evidence và "
            "điều hướng review. Paddle không còn là fallback recognizer. "
            "Kết quả held-out chỉ dùng chẩn đoán, không chỉnh threshold.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-queue", type=Path, required=True)
    parser.add_argument("--development-reviews", type=Path, required=True)
    parser.add_argument("--development-predictions", type=Path, required=True)
    parser.add_argument("--heldout-ground-truth", type=Path, required=True)
    parser.add_argument("--heldout-predictions", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if (
        args.output_json.exists() or args.output_md.exists()
    ) and not args.overwrite:
        raise FileExistsError("Phase 14.8 output exists; refusing overwrite")
    development_queue = load_json(args.development_queue)
    development_reviews = load_json(args.development_reviews)
    development_predictions = load_json(args.development_predictions)
    heldout_ground_truth = load_json(args.heldout_ground_truth)
    heldout_predictions = load_json(args.heldout_predictions)
    development = development_records(
        development_queue,
        development_reviews,
        development_predictions,
    )
    heldout, skipped = heldout_records(
        heldout_ground_truth,
        heldout_predictions,
    )
    payload = build_analysis(
        development=development,
        heldout=heldout,
        heldout_skipped=skipped,
        source_digests={
            "developmentQueueSha256": sha256_file(args.development_queue),
            "developmentReviewsSha256": sha256_file(
                args.development_reviews
            ),
            "developmentPredictionsSha256": sha256_file(
                args.development_predictions
            ),
            "heldOutGroundTruthSha256": sha256_file(
                args.heldout_ground_truth
            ),
            "heldOutPredictionsSha256": sha256_file(
                args.heldout_predictions
            ),
        },
    )
    atomic_write_json(args.output_json, payload)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(build_markdown(payload), encoding="utf-8")
    print(
        "Phase 14.8 complete: "
        f"development={len(development)}, heldout={len(heldout)}, "
        "primary=seq2seq, verifier=transformer, paddle_fallback=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
