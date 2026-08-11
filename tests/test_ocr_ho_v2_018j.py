from scripts.review_ocr_ho_v2_018j import review, validate_lineage


def source(task: str, schema: str) -> dict:
    return {
        "schemaVersion": schema,
        "taskId": task,
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
    }


def lineage_sources() -> tuple[dict, dict, dict]:
    source_018i = source(
        "OCR-HO-V2-018I",
        "ocr-ho-v2-018i-selector-safety-authorization-intake/1.0.0",
    )
    source_018i.update(
        {
            "protocol": {"gate": "AUTO_DETECTOR"},
            "sourceDigests": {"artifact018hSha256": "h"},
            "authorizationIntake": {
                "status": "VALID_FOR_SAFETY_REVIEW",
                "sourceArtifactMatch": True,
                "scopeMatch": True,
                "selectorSafetyEvidenceAuthorized": True,
                "counterfactualAuthorized": False,
                "selectorChangeAuthorized": False,
                "developmentReplayAuthorized": False,
                "heldoutEvaluationAuthorized": False,
                "evaluateOnceAuthorized": False,
                "primaryRuntimeChangeAuthorized": False,
                "productionPromotionAllowed": False,
            },
        }
    )
    source_018h = source(
        "OCR-HO-V2-018H",
        "ocr-ho-v2-018h-selector-safety-evidence-review/1.0.0",
    )
    source_018h.update(
        {
            "protocol": {
                "diagnostic": "AGGREGATE_SELECTOR_SAFETY_EVIDENCE_REVIEW_ONLY"
            },
            "sourceDigests": {"artifact018gSha256": "g"},
        }
    )
    source_018g = source(
        "OCR-HO-V2-018G",
        "ocr-ho-v2-018g-selector-counterfactual-review/1.0.0",
    )
    source_018g.update(
        {
            "protocol": {"diagnostic": "AGGREGATE_SELECTOR_OPENING_REVIEW_ONLY"},
            "selectorOpening": {"allowed": False},
            "decision": {"counterfactualAuthorized": False},
            "openingCriteria": {
                "recognizerDominantEvidence": {
                    "status": "PASS",
                    "observedRate": 0.776,
                    "threshold": 0.5,
                },
                "priorCounterfactualNonRegression": {
                    "status": "FAIL",
                    "derDelta": 0.007905,
                    "diacriticErrorDelta": 2,
                    "strictExactDelta": -1,
                },
                "strictRuleEligibleSwitch": {
                    "status": "FAIL",
                    "eligibleSwitchCount": 0,
                    "changedFieldCount": 0,
                },
                "replayChangedFieldEvidence": {
                    "status": "FAIL",
                    "eligibleSwitchCount": 0,
                    "changedFieldCount": 0,
                },
            },
            "evidence": {
                "018F": {
                    "recognizerDisagreementCount": 291,
                    "autoRegionHitErrorGroupCount": 375,
                }
            },
        }
    )
    return source_018i, source_018h, source_018g


def test_aggregate_safety_evidence_stays_hold() -> None:
    source_018i, source_018h, source_018g = lineage_sources()
    report = review(
        source_018i,
        source_018h,
        source_018g,
        {
            "artifact018iSha256": "i",
            "artifact018hSha256": "h",
            "artifact018gSha256": "g",
        },
    )
    assert report["decision"]["status"] == "AGGREGATE_SELECTOR_SAFETY_EVIDENCE_HOLD"
    assert report["readiness"]["safetyEvidenceCollected"] is True
    assert report["readiness"]["selectorCounterfactualOpeningAllowed"] is False
    assert report["gates"]["acceptedCoverage"] == 0


def test_lineage_rejects_broader_authorization() -> None:
    source_018i, source_018h, source_018g = lineage_sources()
    source_018i["authorizationIntake"]["counterfactualAuthorized"] = True
    try:
        validate_lineage(
            source_018i,
            source_018h,
            source_018g,
            {
                "artifact018iSha256": "i",
                "artifact018hSha256": "h",
                "artifact018gSha256": "g",
            },
        )
    except SystemExit as exc:
        assert "broader authorization" in str(exc)
    else:
        raise AssertionError("broader authorization must fail closed")
