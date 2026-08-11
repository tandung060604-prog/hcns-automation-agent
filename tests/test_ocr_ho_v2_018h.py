from scripts.review_ocr_ho_v2_018h import review


def test_safety_evidence_stays_hold_without_independent_proof() -> None:
    source = {
        "schemaVersion": "ocr-ho-v2-018g-selector-counterfactual-review/1.0.0",
        "taskId": "OCR-HO-V2-018G",
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
        "openingCriteria": {
            "recognizerDominantEvidence": {"status": "PASS", "observedRate": 0.776},
            "priorCounterfactualNonRegression": {
                "status": "FAIL",
                "derDelta": 0.007905,
                "diacriticErrorDelta": 2,
            },
            "strictRuleEligibleSwitch": {
                "status": "FAIL",
                "eligibleSwitchCount": 0,
            },
            "replayChangedFieldEvidence": {
                "status": "FAIL",
                "changedFieldCount": 0,
            },
        },
        "gates": {
            "schemaErrors": 0,
            "sensitiveFalseAcceptance": 0,
            "acceptedCoverage": 0,
            "manualReviewOnly": True,
        },
        "selectorOpening": {"allowed": False},
        "decision": {"counterfactualAuthorized": False},
    }
    report = review(source, "digest")
    assert report["readiness"]["independentSafetyEvidenceReady"] is False
    assert report["readiness"]["counterfactualOpeningAllowed"] is False
    assert report["decision"]["status"] == "SELECTOR_SAFETY_EVIDENCE_HOLD"
    assert report["gates"]["acceptedCoverage"] == 0
