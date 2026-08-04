from unittest import TestCase

from synthetic_fixtures import synthetic_cv_pdf_bytes

from hcns_agent.adapters.camunda7.contract import (
    DMN_QUALITY_INPUT_VARIABLES,
    CamundaQualityAction,
    CamundaRolloutPolicy,
    CamundaWorkflowDocumentType,
    QualityRoutingInputs,
    build_quality_process_variables,
    classification_status,
    map_document_type,
    route_quality,
    validate_dmn_quality_variables,
    validate_process_variables,
)
from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.bootstrap import build_default_pipeline
from hcns_agent.domain.documents import DocumentType
from hcns_agent.ports.document_parser import DocumentSource


def _routing(**overrides: object) -> QualityRoutingInputs:
    values: dict[str, object] = {
        "quality_status": "PASS",
        "review_required": False,
        "sensitive_field_needs_review": False,
        "missing_critical_field": False,
        "business_inconsistency": False,
        "required_fields_complete": True,
        "overall_confidence": 0.95,
        "auto_continue_enabled": False,
    }
    values.update(overrides)
    return QualityRoutingInputs(**values)  # type: ignore[arg-type]


class CamundaContractTests(TestCase):
    def test_document_type_mapping_is_explicit_and_lossless_at_domain_boundary(self) -> None:
        self.assertIs(
            CamundaWorkflowDocumentType.IDENTITY_DOCUMENT,
            map_document_type(DocumentType.IDENTITY_CARD),
        )
        self.assertIs(
            CamundaWorkflowDocumentType.IDENTITY_DOCUMENT,
            map_document_type(DocumentType.PASSPORT),
        )
        self.assertIs(
            CamundaWorkflowDocumentType.EMPLOYEE_INFORMATION_FORM,
            map_document_type(DocumentType.EMPLOYEE_PROFILE),
        )
        self.assertIs(
            CamundaWorkflowDocumentType.EMPLOYMENT_CONTRACT,
            map_document_type(DocumentType.CONTRACT_APPENDIX),
        )
        self.assertIs(CamundaWorkflowDocumentType.CV, map_document_type(DocumentType.CV))
        self.assertIs(
            CamundaWorkflowDocumentType.OTHER_HR_DOCUMENT,
            map_document_type(DocumentType.UNKNOWN),
        )

    def test_classification_status_handles_match_mismatch_unknown_and_invalid(self) -> None:
        self.assertEqual("CONFIRMED", classification_status("CV", DocumentType.CV))
        self.assertEqual(
            "MISMATCH",
            classification_status("TIMESHEET", DocumentType.CV),
        )
        self.assertEqual(
            "UNKNOWN",
            classification_status("OTHER_HR_DOCUMENT", DocumentType.UNKNOWN),
        )
        self.assertEqual("INVALID", classification_status("RAW-CUSTOM-TYPE", DocumentType.CV))

    def test_quality_variables_are_sanitized_and_sensitive_cv_requires_review(self) -> None:
        result = build_default_pipeline(DeterministicMockOcrEngine()).execute(
            DocumentSource(
                document_id="SYN-CAMUNDA-CV",
                filename="cv.pdf",
                content=synthetic_cv_pdf_bytes(),
                source_reference="object://synthetic/cv",
            )
        )

        variables = build_quality_process_variables(result)

        self.assertEqual("CV", variables["detectedDocumentType"])
        self.assertEqual("CV", variables["workflowDocumentType"])
        self.assertTrue(variables["reviewRequired"])
        self.assertTrue(variables["sensitiveFieldNeedsReview"])
        self.assertFalse(variables["autoContinueEnabled"])
        self.assertNotIn("fields", variables)
        self.assertNotIn("rawText", variables)

    def test_quality_routing_applies_safety_precedence_and_shadow_gate(self) -> None:
        self.assertIs(
            CamundaQualityAction.REQUEST_REUPLOAD,
            route_quality(_routing(quality_status="REJECTED")),
        )
        self.assertIs(
            CamundaQualityAction.REQUEST_REUPLOAD,
            route_quality(_routing(missing_critical_field=True)),
        )
        self.assertIs(
            CamundaQualityAction.HR_REVIEW,
            route_quality(
                _routing(
                    sensitive_field_needs_review=True,
                    auto_continue_enabled=True,
                )
            ),
        )
        self.assertIs(
            CamundaQualityAction.HR_REVIEW,
            route_quality(_routing(business_inconsistency=True)),
        )
        self.assertIs(
            CamundaQualityAction.HR_REVIEW,
            route_quality(_routing(required_fields_complete=False)),
        )
        self.assertIs(
            CamundaQualityAction.REQUEST_REUPLOAD,
            route_quality(_routing(overall_confidence=0.59)),
        )
        self.assertIs(
            CamundaQualityAction.USER_REVIEW,
            route_quality(_routing(auto_continue_enabled=False)),
        )
        self.assertIs(
            CamundaQualityAction.AUTO_CONTINUE,
            route_quality(_routing(auto_continue_enabled=True)),
        )
        self.assertIs(
            CamundaQualityAction.USER_REVIEW,
            route_quality(_routing(overall_confidence=0.75)),
        )

        with self.assertRaises(ValueError):
            CamundaRolloutPolicy(
                policy_id="unsafe-shadow",
                version="1.0.0",
                mode="SHADOW",
                auto_continue_enabled=True,
                real_side_effects_enabled=False,
            )

    def test_process_variable_whitelist_rejects_raw_or_structured_payloads(self) -> None:
        validate_process_variables(
            {
                "documentReference": "object://synthetic/document",
                "qualityStatus": "PASS",
                "reviewRequired": False,
            }
        )
        with self.assertRaises(ValueError):
            validate_process_variables({"rawOcrText": "forbidden"})
        with self.assertRaises(TypeError):
            validate_process_variables({"resultReference": {"uri": "forbidden"}})  # type: ignore[dict-item]

    def test_dmn_quality_contract_requires_exactly_eight_typed_inputs(self) -> None:
        variables = {
            "qualityStatus": "REVIEW_REQUIRED",
            "reviewRequired": True,
            "sensitiveFieldNeedsReview": False,
            "missingCriticalField": False,
            "businessInconsistency": False,
            "requiredFieldsComplete": True,
            "overallConfidence": 0.85,
            "autoContinueEnabled": False,
        }

        self.assertEqual(DMN_QUALITY_INPUT_VARIABLES, frozenset(variables))
        validate_dmn_quality_variables(variables)
        with self.assertRaises(ValueError):
            validate_dmn_quality_variables(
                {name: value for name, value in variables.items() if name != "reviewRequired"}
            )
        with self.assertRaises(TypeError):
            validate_dmn_quality_variables({**variables, "reviewRequired": 1})
        with self.assertRaises(ValueError):
            validate_dmn_quality_variables({**variables, "overallConfidence": 1.1})
