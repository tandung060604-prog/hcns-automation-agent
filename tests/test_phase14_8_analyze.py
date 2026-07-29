from __future__ import annotations

from scripts.phase14_8_analyze import (
    Record,
    analyze_corpus,
    build_analysis,
    development_records,
)


def records() -> list[Record]:
    return [
        Record(
            document_key="synthetic-a",
            reference="CỘNG HÒA",
            primary="CONG HOA",
            transformer="CỘNG HÒA",
            primary_confidence=0.4,
        ),
        Record(
            document_key="synthetic-b",
            reference="ĐƠN XIN NGHỈ PHÉP",
            primary="ĐƠN XIN NGHỈ PHÉP",
            transformer="ĐƠN XIN NGHỈ PHÉP",
            primary_confidence=0.9,
        ),
        Record(
            document_key="synthetic-b",
            reference="NHÂN VIÊN",
            primary="NHÂN VIÊN",
            transformer="NHAN VIEN",
            primary_confidence=0.8,
        ),
    ]


def test_verifier_policy_never_changes_primary_or_uses_paddle() -> None:
    payload = analyze_corpus(records())

    assert payload["policyReplay"]["selectedTextChangedCount"] == 0
    assert payload["policyReplay"]["paddleEligibleForSelection"] is False
    assert payload["policyReplay"]["verifiedLineCount"] == 1
    assert payload["primaryErrorAnalysis"]["transformerExactRecoveryCount"] == 1
    assert (
        payload["primaryErrorAnalysis"]["transformerLossIfBlindlySelectedCount"]
        == 1
    )


def test_aggregate_analysis_contains_no_private_text_or_document_key() -> None:
    payload = build_analysis(
        development=records(),
        heldout=records(),
        heldout_skipped=0,
        source_digests={"source": "a" * 64},
    )
    rendered = str(payload)

    assert payload["containsRealPII"] is False
    assert "CỘNG HÒA" not in rendered
    assert "synthetic-a" not in rendered
    assert payload["decision"]["paddleFallbackEnabled"] is False
    assert payload["decision"]["heldOutUsedForThresholdTuning"] is False


def test_development_loader_uses_confirmed_reviews_not_queue_draft() -> None:
    queue = {
        "queueDigest": "digest",
        "lineCount": 1,
        "documentCount": 1,
        "cases": [
            {
                "caseId": "line-1",
                "documentKey": "synthetic-doc",
                "groundTruth": "DRAFT SAI",
            }
        ],
    }
    reviews = {
        "reviews": {
            "line-1": {
                "groundTruth": "GROUND TRUTH ĐÚNG",
                "comparedWithCrop": True,
                "allTextChecked": True,
            }
        }
    }
    predictions = {
        "queueDigest": "digest",
        "predictionsHiddenDuringReview": True,
        "cases": [
            {
                "caseId": "line-1",
                "predictions": {
                    "vietocr_vgg_seq2seq": {
                        "text": "GROUND TRUTH ĐÚNG",
                        "confidence": 0.9,
                    },
                    "vietocr_vgg_transformer": {
                        "text": "GROUND TRUTH ĐÚNG"
                    },
                },
            }
        ],
    }

    loaded = development_records(queue, reviews, predictions)

    assert loaded[0].reference == "GROUND TRUTH ĐÚNG"
