"""Versioned Business JSON projection for a validated IDP result."""

from __future__ import annotations

from hcns_agent.domain.canonical import BoundingBox, SourceLocation
from hcns_agent.domain.understanding import IdpResult, ValidationIssue


class BusinessJsonBuilder:
    def build(self, result: IdpResult) -> dict[str, object]:
        classification = result.classification
        quality = result.quality
        return {
            "schemaVersion": result.schema_version,
            "documentId": result.document_id,
            "sourceFormat": result.canonical_document.source_format.value,
            "documentType": classification.document_type.value,
            "classification": {
                "confidence": classification.confidence,
                "classifier": {
                    "name": classification.classifier_name,
                    "version": classification.classifier_version,
                },
                "candidates": [
                    {
                        "documentType": candidate.document_type.value,
                        "confidence": candidate.confidence,
                        "matchedMarkers": list(candidate.matched_markers),
                    }
                    for candidate in classification.candidates
                ],
            },
            "reviewStatus": ("PENDING" if quality.review_required else "NOT_REQUIRED"),
            "quality": {
                "score": quality.score,
                "status": quality.status.value,
                "reviewRequired": quality.review_required,
                "reasons": list(quality.reasons),
                "issues": [_issue(issue) for issue in quality.issues],
            },
            "fields": [
                {
                    "name": field.name,
                    "value": field.value,
                    "confidence": field.confidence,
                    "status": field.status.value,
                    "sensitive": field.sensitive,
                    "extractor": {
                        "name": field.extractor_name,
                        "version": field.extractor_version,
                    },
                    "provenance": [
                        {
                            "method": evidence.method,
                            "source": _source_location(evidence.source),
                        }
                        for evidence in field.evidence
                    ],
                }
                for field in result.fields
            ],
        }


def _issue(issue: ValidationIssue) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": issue.code,
        "message": issue.message,
        "severity": issue.severity.value,
    }
    if issue.field_name is not None:
        payload["fieldName"] = issue.field_name
    if issue.source is not None:
        payload["source"] = _source_location(issue.source)
    return payload


def _source_location(source: SourceLocation) -> dict[str, object]:
    payload: dict[str, object] = {}
    values = {
        "sourceReference": source.source_reference,
        "pageIndex": source.page_index,
        "blockIndex": source.block_index,
        "sheetName": source.sheet_name,
        "rowIndex": source.row_index,
        "columnIndex": source.column_index,
    }
    payload.update({key: value for key, value in values.items() if value is not None})
    if source.bounding_box is not None:
        payload["boundingBox"] = _bounding_box(source.bounding_box)
    return payload


def _bounding_box(box: BoundingBox) -> dict[str, object]:
    return {
        "x0": box.x0,
        "y0": box.y0,
        "x1": box.x1,
        "y1": box.y1,
        "coordinateSpace": box.coordinate_space,
    }
