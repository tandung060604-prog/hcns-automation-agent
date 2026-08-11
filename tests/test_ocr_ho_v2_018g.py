from scripts.review_ocr_ho_v2_018g import review


def source(task: str, schema: str) -> dict:
    return {
        "taskId": task,
        "schemaVersion": schema,
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "containsRawPII": False,
        "predictionOpened": False,
        "gtUsedAtSelection": False,
    }


def test_selector_opening_stays_denied_after_der_regression() -> None:
    source_018f = source("OCR-HO-V2-018F", "ocr-ho-v2-018f-recognizer-token-attribution/1.0.0")
    source_018f.update(
        {
            "candidateRule": {"selectionEligible": False},
            "decision": {"counterfactualAuthorized": False, "dominantCohort": "AUTO_REGION_HIT"},
            "attribution": {
                "autoRegionHit": {
                    "recognizerDominantAttribution": True,
                    "recognizerDisagreementRate": 0.776,
                    "recognizerDisagreementCount": 291,
                    "errorGroupCount": 375,
                    "tokenMismatchCount": 11,
                    "lineOrderMismatchCount": 72,
                }
            },
        }
    )
    source_017d = source("OCR-HO-V2-017D", "ocr-ho-v2-017d-selector-counterfactual/1.0.0")
    source_017d.update(
        {
            "gates": {"derNotWorse": False},
            "metrics": {
                "selected_11_10_2": {
                    "der": 0.162055,
                    "diacriticErrorCount": 41,
                    "strictExactCount": 76,
                },
                "counterfactual_017d": {
                    "der": 0.16996,
                    "diacriticErrorCount": 43,
                    "strictExactCount": 75,
                },
            },
        }
    )
    source_017e = source("OCR-HO-V2-017E", "ocr-ho-v2-017e-selector-rule-review/1.0.0")
    source_017e["selectionAudit"] = {"eligibleSwitchCount": 0, "changedFieldCount": 0}
    source_017f = source("OCR-HO-V2-017F", "ocr-ho-v2-017f-selector-replay/1.0.0")
    source_017f["selectionAudit"] = {"eligibleSwitchCount": 0, "changedFieldCount": 0}
    report = review(source_018f, source_017d, source_017e, source_017f, {})
    assert report["selectorOpening"] == {
        "allowed": False,
        "status": "DENIED_HOLD",
        "counterfactualAuthorized": False,
        "ownerAuthorizationPresent": False,
        "reason": (
            "Recognizer dominance alone is insufficient: prior counterfactual DER and "
            "diacritic errors increased, while strict rule/replay produced no switch or "
            "changed field."
        ),
    }
    assert report["decision"]["status"] == "NO_COUNTERFACTUAL_AUTHORIZATION_HOLD"
    assert report["gates"]["acceptedCoverage"] == 0
