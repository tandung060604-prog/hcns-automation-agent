from scripts.analyze_ocr_ho_v2_018f import review, summarize_bucket


def scope(schema: str, task_id: str) -> dict:
    return {
        "schemaVersion": schema,
        "taskId": task_id,
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "diagnosticFieldCount": 45,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
        "protocol": {"gate": "AUTO_DETECTOR", "diagnostic": "ORACLE_LINE_TOKEN_ATTRIBUTION_ONLY"},
    }


def bucket(**counts: int) -> dict:
    names = {
        "LINE_ID_MISS": 0,
        "LINE_ORDER_MISMATCH": 0,
        "TOKEN_OMISSION": 0,
        "TOKEN_EXTRA": 0,
        "TOKEN_SWAP": 0,
        "DUPLICATE_LINE": 0,
        "RECOGNIZER_DISAGREEMENT": 0,
    }
    names.update(counts)
    return {"groups": sum(names.values()), "eligibleLineTokenGroups": 1, "classCounts": names}


def test_summarize_bucket_keeps_token_and_recognizer_classes_separate() -> None:
    result = summarize_bucket(bucket(RECOGNIZER_DISAGREEMENT=4, TOKEN_EXTRA=2))
    assert result["recognizerDisagreementCount"] == 4
    assert result["tokenMismatchCount"] == 2
    assert result["dominantErrorClass"] == "RECOGNIZER_DISAGREEMENT"


def test_review_is_hold_and_never_authorizes_selection() -> None:
    aggregate = {
        "AUTO_REGION_HIT": bucket(RECOGNIZER_DISAGREEMENT=6, LINE_ORDER_MISMATCH=2),
        "AUTO_REGION_MISS": bucket(LINE_ID_MISS=3),
    }
    by_field = {
        field: {
            "AUTO_REGION_HIT": bucket(RECOGNIZER_DISAGREEMENT=2),
            "AUTO_REGION_MISS": bucket(LINE_ID_MISS=1),
        }
        for field in ("fullName", "placeOfOrigin", "placeOfResidence")
    }
    by_profile = {"synthetic": aggregate}
    source_017k = scope("ocr-ho-v2-017k-line-token-diagnostic/1.0.0", "OCR-HO-V2-017K")
    source_017k["aggregate"] = {"classCounts": {"PARSER_CONTAMINATION": 0}}
    source_017m = scope("ocr-ho-v2-017m-line-token-cohort-separation/1.0.0", "OCR-HO-V2-017M")
    source_017m["cohorts"] = {
        "aggregate": aggregate,
        "byField": by_field,
        "byProfile": by_profile,
        "byVariant": by_profile,
    }
    source_018e = scope("ocr-ho-v2-018e-boundary-reconciliation/1.0.0", "OCR-HO-V2-018E")
    source_018e.update({
        "decision": {
            "status": "BOUNDARY_RECONCILED_HOLD",
            "runtimeChanged": False,
            "replayExecuted": False,
        },
        "gates": {"patchAuthorized": False},
        "reconciliation": {"roiConsistency": {"allFieldsConsistent": True}},
    })
    report = review(source_017k, source_017m, source_018e, {})
    assert report["decision"]["status"] == "RECOGNIZER_TOKEN_ATTRIBUTION_HOLD"
    assert report["attribution"]["autoRegionHit"]["recognizerDisagreementRate"] == 0.75
    assert report["candidateRule"]["selectionEligible"] is False
    assert report["gates"]["acceptedCoverage"] == 0
