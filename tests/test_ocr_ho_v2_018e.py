from __future__ import annotations

from scripts.analyze_ocr_ho_v2_018e import reconcile

# ruff: noqa: E501


def scope(schema: str, task: str | None = None) -> dict[str, object]:
    value: dict[str, object] = {
        "schemaVersion": schema,
        "datasetFamily": "CCCD",
        "datasetId": "DATA-HO-014",
        "datasetRole": "DEVELOPMENT_REGRESSION",
        "documentCount": 15,
        "evaluatedFieldCount": 120,
        "candidateVersion": "11.10.2",
        "baselineVersion": "11.9.1",
        "containsRawPII": False,
        "predictionOpened": False,
    }
    if task:
        value["taskId"] = task
    return value


def test_reconciliation_stays_aggregate_only_and_does_not_authorize_patch() -> None:
    fields = {
        name: {"autoHit": 8, "evaluated": 15, "boundaryMiss": 7, "categoryCounts": {}}
        for name in ("fullName", "placeOfOrigin", "placeOfResidence")
    }
    fields["placeOfOrigin"]["autoHit"] = 9
    fields["placeOfOrigin"]["boundaryMiss"] = 6
    fields["placeOfResidence"]["autoHit"] = 10
    fields["placeOfResidence"]["boundaryMiss"] = 5
    source_018d = {
        **scope("ocr-ho-v2-018d-gate-failure-review/1.0.0", "OCR-HO-V2-018D"),
        "decision": {"selectedLayer": "DETECTOR_CROP"},
        "gateFailureSummary": {
            "targetROI": {
                name: {"correct": item["autoHit"], "evaluated": 15}
                for name, item in fields.items()
            }
        },
    }
    source_017n = {
        **scope("ocr-ho-v2-017n-auto-line-mapping-boundary-attribution/1.0.0", "OCR-HO-V2-017N"),
        "evidence": {
            "automaticDetectorByField": fields,
            "automaticDetectorAggregate": {"dominantCategoryRate": 0.444444, "categoryCounts": {}},
            "lineSideCounts": {},
        },
    }
    source_017o = {
        **scope("ocr-ho-v2-017o-residence-bottom-boundary-attribution/1.0.0", "OCR-HO-V2-017O"),
        "evidence": {
            "residenceBoundaryMisses": {
                "bottomBoundary": {"caseCount": 3, "caseRate": 0.6, "regionSourceCounts": {"phase11_10_geometry_line_segmentation": 3}}
            }
        },
    }
    source_017p = {
        **scope("ocr-ho-v2-017p-residence-geometry-segmentation-boundary-review/1.0.0", "OCR-HO-V2-017P"),
        "evidence": {"bottomBoundaryCases": {"regionSourceCounts": {"phase11_10_geometry_line_segmentation": 3}, "sealedLineIdOverlapRate": 0.0, "bottomOverflowCaseRate": 0.666667}},
    }
    source_017k = {
        **scope("ocr-ho-v2-017k-line-token-diagnostic/1.0.0", "OCR-HO-V2-017K"),
        "aggregate": {"classCounts": {"LINE_ORDER_MISMATCH": 72, "RECOGNIZER_DISAGREEMENT": 291}, "eligibleFailureCount": 630},
    }
    source_018a = {
        **scope("ocr-ho-v2-018a-shadow-patch-review/1.0.0", "OCR-HO-V2-018A"),
        "review": {"qualityImprovementProven": False},
    }
    report = reconcile(source_018d, source_017n, source_017o, source_017p, source_017k, source_018a, {})
    assert report["decision"]["status"] == "BOUNDARY_RECONCILED_HOLD"
    assert report["reconciliation"]["roiConsistency"]["allFieldsConsistent"] is True
    assert report["selectedNextDiagnostic"]["taskId"] == "OCR-HO-V2-018F"
    assert report["selectedNextDiagnostic"]["patchAuthorized"] is False
    assert report["gates"]["acceptedCoverage"] == 0
