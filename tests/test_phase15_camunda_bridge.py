from __future__ import annotations

import pytest

from apps.ocr_lab.api.phase15_idp import (
    build_phase15_business_json,
    classify_phase15_document,
    extract_phase15_document,
)
from hcns_agent.adapters.camunda7.phase15_bridge import (
    Phase15CamundaProjectionError,
    project_phase15_business_json,
)


def _canonical_document(lines: list[str]) -> dict[str, object]:
    blocks = [
        {
            "blockIndex": index,
            "text": line,
            "sourceKind": "pdf_text_layer",
            "confidence": 1.0,
            "evidence": {
                "pageIndex": 0,
                "sourceRef": f"synthetic:line:{index}",
                "bbox": None,
            },
        }
        for index, line in enumerate(lines)
    ]
    return {
        "schemaVersion": "1.0.0",
        "sourceFormat": "PDF",
        "adapter": "synthetic_native",
        "ingestionMode": "NATIVE",
        "pageCount": 1,
        "pages": [
            {
                "pageIndex": 0,
                "ingestionMode": "native",
                "blocks": blocks,
                "nativeBlocks": blocks,
                "ocrBlocks": [],
            }
        ],
        "tables": [],
        "plainText": "\n".join(lines),
        "metadata": {},
    }


def _business_json() -> dict[str, object]:
    return {
        "schemaVersion": "2.0.0",
        "schemaRef": "synthetic/phase15-schema",
        "documentId": "SYNTHETIC-DOC-01",
        "camunda": {
            "businessKey": "SYNTHETIC-DOC-01",
            "variables": {
                "workflowDocumentType": "LEAVE_REQUEST",
                "sourceFormat": "DOCX",
                "classificationStatus": "accepted",
                "classificationConfidence": 1.0,
                "reviewRequired": True,
            },
        },
    }


def test_phase15_projection_normalizes_status_and_forces_shadow_policy() -> None:
    projection = project_phase15_business_json(
        _business_json(),
        application_id="SYNTHETIC-APP-01",
        document_reference="SYNTHETIC-DOC-01",
        declared_document_type="LEAVE_REQUEST",
        result_reference="SYNTHETIC-RESULT-01",
    )

    assert projection.business_key == "SYNTHETIC-DOC-01"
    assert projection.variables["classificationStatus"] == "CONFIRMED"
    assert projection.variables["autoContinueEnabled"] is False
    assert "fields" not in projection.variables
    assert all("/" not in str(value) for value in projection.variables.values())


def test_phase15_projection_rejects_path_and_raw_camunda_values() -> None:
    payload = _business_json()
    variables = payload["camunda"]["variables"]  # type: ignore[index]
    variables["documentSourcePath"] = r"C:\private\synthetic.docx"  # type: ignore[index]

    with pytest.raises(Phase15CamundaProjectionError, match="forbidden"):
        project_phase15_business_json(
            payload,
            application_id="SYNTHETIC-APP-01",
            document_reference="SYNTHETIC-DOC-01",
            declared_document_type="LEAVE_REQUEST",
            result_reference="SYNTHETIC-RESULT-01",
        )


def test_phase15_projection_rejects_workflow_type_mismatch() -> None:
    payload = _business_json()
    variables = payload["camunda"]["variables"]  # type: ignore[index]
    variables["workflowDocumentType"] = "OVERTIME_REQUEST"  # type: ignore[index]

    with pytest.raises(Phase15CamundaProjectionError, match="does not match"):
        project_phase15_business_json(
            payload,
            application_id="SYNTHETIC-APP-01",
            document_reference="SYNTHETIC-DOC-01",
            declared_document_type="LEAVE_REQUEST",
            result_reference="SYNTHETIC-RESULT-01",
        )


def test_projection_accepts_actual_phase15_business_json_shape() -> None:
    canonical = _canonical_document(
        ["PHIẾU ĐĂNG KÝ LÀM THÊM GIỜ", "Mã nhân viên: SYN-001"]
    )
    classification = classify_phase15_document(canonical)
    extraction = extract_phase15_document(canonical, classification)
    business = build_phase15_business_json(
        "SYNTHETIC-DOC-01",
        canonical,
        classification,
        extraction,
        contains_real_pii=False,
    )

    projection = project_phase15_business_json(
        business,
        application_id="SYNTHETIC-APP-01",
        document_reference="SYNTHETIC-DOC-01",
        declared_document_type="OVERTIME_REQUEST",
        result_reference="SYNTHETIC-RESULT-01",
    )

    assert projection.variables["classificationStatus"] == "CONFIRMED"
    assert projection.variables["workflowDocumentType"] == "OVERTIME_REQUEST"
    assert projection.variables["resultReference"] == "SYNTHETIC-RESULT-01"
