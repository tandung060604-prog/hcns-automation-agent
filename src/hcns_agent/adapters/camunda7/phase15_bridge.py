"""Sanitized Phase15 Business JSON projection for the Camunda boundary."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from hcns_agent.adapters.camunda7.contract import (
    ProcessVariables,
    validate_process_variables,
)

_OPAQUE_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_FORBIDDEN_CAMUNDA_NAMES = frozenset(
    {
        "idpPayload",
        "rawFile",
        "ocrText",
        "recognizedText",
        "fields",
        "tables",
        "documentSourcePath",
    }
)
_PROJECTION_NAMES = frozenset(
    {
        "sourceFormat",
        "classificationStatus",
        "classificationConfidence",
        "parseStatus",
        "qualityStatus",
        "reviewRequired",
        "sensitiveFieldNeedsReview",
        "requiredFieldsComplete",
        "workflowDocumentType",
        "schemaVersion",
    }
)
_CLASSIFICATION_STATUS_MAP = {
    "accepted": "CONFIRMED",
    "confirmed": "CONFIRMED",
    "needs_review": "UNKNOWN",
    "mismatch": "MISMATCH",
    "unknown": "UNKNOWN",
    "rejected": "INVALID",
    "invalid": "INVALID",
}


class Phase15CamundaProjectionError(ValueError):
    """Phase15 output cannot cross the sanitized Camunda boundary."""


@dataclass(frozen=True, slots=True)
class Phase15CamundaProjection:
    business_key: str
    variables: ProcessVariables


def project_phase15_business_json(
    business_json: Mapping[str, object],
    *,
    application_id: str,
    document_reference: str,
    declared_document_type: str,
    result_reference: str,
) -> Phase15CamundaProjection:
    """Project Phase15 metadata without copying fields, OCR or local paths.

    The caller supplies all references because Phase15's default artifact names
    are private filesystem-relative paths, not Camunda references.
    """

    _opaque(application_id, "application_id")
    _opaque(document_reference, "document_reference")
    _opaque(result_reference, "result_reference")
    _opaque(declared_document_type, "declared_document_type")

    camunda = _mapping(business_json, "camunda")
    source_variables = _mapping(camunda, "variables")
    leaked = _FORBIDDEN_CAMUNDA_NAMES & set(source_variables)
    if leaked:
        raise Phase15CamundaProjectionError(
            f"Phase15 Camunda variables contain forbidden names: {sorted(leaked)}"
        )
    business_key = camunda.get("businessKey", business_json.get("documentId"))
    if not isinstance(business_key, str):
        raise Phase15CamundaProjectionError("Phase15 business key is missing")
    _opaque(business_key, "business_key")

    variables: ProcessVariables = {
        "applicationId": application_id,
        "documentReference": document_reference,
        "declaredDocumentType": declared_document_type,
        "resultReference": result_reference,
        "autoContinueEnabled": False,
    }
    for name in _PROJECTION_NAMES:
        value = source_variables.get(name)
        if value is None:
            continue
        if isinstance(value, (dict, list, tuple, set)):
            raise Phase15CamundaProjectionError(
                f"Phase15 variable {name} must be scalar"
            )
        if name == "classificationStatus":
            if not isinstance(value, str):
                raise Phase15CamundaProjectionError(
                    "Phase15 classificationStatus must be a string"
                )
            normalized = _CLASSIFICATION_STATUS_MAP.get(value.casefold())
            if normalized is None:
                raise Phase15CamundaProjectionError(
                    "Phase15 classificationStatus is unsupported"
                )
            value = normalized
        variables[name] = value  # type: ignore[assignment]

    workflow_type = source_variables.get("workflowDocumentType")
    if workflow_type is not None and workflow_type != declared_document_type:
        raise Phase15CamundaProjectionError(
            "Phase15 workflowDocumentType does not match declared type"
        )
    variables["workflowDocumentType"] = declared_document_type
    validate_process_variables(variables)
    if any(isinstance(value, str) and _looks_like_path(value) for value in variables.values()):
        raise Phase15CamundaProjectionError(
            "Camunda projection contains a filesystem-like reference"
        )
    return Phase15CamundaProjection(business_key=business_key, variables=variables)


def _mapping(value: Mapping[str, object], name: str) -> Mapping[str, object]:
    nested = value.get(name)
    if not isinstance(nested, Mapping):
        raise Phase15CamundaProjectionError(f"Phase15 {name} mapping is missing")
    return nested


def _opaque(value: str, name: str) -> None:
    if _OPAQUE_REFERENCE.fullmatch(value) is None:
        raise Phase15CamundaProjectionError(f"{name} must be an opaque reference")


def _looks_like_path(value: str) -> bool:
    return (
        "/" in value
        or "\\" in value
        or bool(re.match(r"^[A-Za-z]:", value))
        or value.startswith((".", "~"))
    )
