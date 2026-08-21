"""Run DATA-31 through the promoted Template-first service in private storage."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "apps" / "ocr_lab" / "api"))

from external_dataset_prediction import (  # noqa: E402
    FIELD_SPECS,
    MATCHING_POLICY_V2,
    build_aggregate_report,
)

from hcns_agent.adapters.external_dataset import count_source_format_and_pages  # noqa: E402
from hcns_agent.application.external_dataset import (  # noqa: E402
    read_inventory,
    validate_inventory,
)
from hcns_agent.ports.document_parser import DocumentSource  # noqa: E402
from hcns_agent.templates.service import (  # noqa: E402
    build_local_template_processing_service,
)
from hcns_agent.templates.structured_hr import (  # noqa: E402
    STRUCTURED_HR_PARSER_ID,
    STRUCTURED_HR_PARSER_VERSION,
)

PREDICTION_SCHEMA = "external-dataset-predictions/data31-template-first/1.0.0"
SUMMARY_SCHEMA = "pdf001i-data31-quality-recovery/1.0.0"
STRICT_GATE_EXACT = 121
STRICT_GATE_FIELDS = 126
DOCUMENT_TYPE_BY_CATEGORY = {
    "cv": "CV",
    "contract": "EMPLOYMENT_CONTRACT",
    "ielts": "CERTIFICATE",
}
MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--prediction", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--coverage-decision", type=Path)
    parser.add_argument("--ocr-backend", choices=("easyocr", "paddle"), default="easyocr")
    parser.add_argument("--device", default="cpu")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_root = args.dataset_root.expanduser().resolve(strict=True)
    inventory_path = args.inventory.expanduser().resolve(strict=True)
    ground_truth_path = args.ground_truth.expanduser().resolve(strict=True)
    prediction_path = _new_private_path(args.prediction)
    report_path = _new_private_path(args.report)
    summary_path = _new_private_path(args.summary)
    inventory = read_inventory(inventory_path)
    validate_inventory(
        dataset_root,
        inventory,
        page_counter=count_source_format_and_pages,
    )
    if inventory["dataset"]["datasetId"] != "DATA-31":
        raise SystemExit("This runner only accepts DATA-31")
    ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    coverage_decision = (
        _read_private_json(args.coverage_decision) if args.coverage_decision else None
    )
    evaluation_ground_truth, field_scope, coverage = build_data31_coverage_scope(
        inventory,
        ground_truth,
        coverage_decision,
    )

    service = build_local_template_processing_service(
        device=args.device,
        ocr_backend=args.ocr_backend,
    )
    service.warm_up_ocr()
    prediction = _predict(dataset_root, inventory, service, ocr_backend=args.ocr_backend)
    _write_private(prediction_path, prediction)
    aggregate = build_aggregate_report(
        prediction,
        evaluation_ground_truth,
        policy_version=MATCHING_POLICY_V2,
        field_scope=field_scope,
    )
    _write_private(report_path, aggregate)
    summary = _summary(
        prediction,
        aggregate,
        evaluation_ground_truth,
        prediction_path,
        report_path,
        field_scope=field_scope,
        coverage=coverage,
    )
    out_of_scope_count = coverage["outOfScopeFieldCount"] if coverage else 0
    _write_private(summary_path, summary)
    print(
        "DATA-31 Template-first replay: "
        f"exact={aggregate['metrics']['fieldExactMatchCount']}/{aggregate['fieldCount']} "
        f"accepted={aggregate['metrics']['fieldAcceptedMatchCount']}/{aggregate['fieldCount']} "
        f"outOfScope={out_of_scope_count} "
        f"schemaErrors={aggregate['schemaErrors']} decision={aggregate['decision']}"
    )
    return 0


def _predict(
    dataset_root: Path,
    inventory: dict[str, Any],
    service: Any,
    *,
    ocr_backend: str,
) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    for record in inventory["cases"]:
        category = str(record["category"])
        source_path = (dataset_root / Path(str(record["sourceRelativePath"]))).resolve(strict=True)
        media_type = MEDIA_TYPES.get(source_path.suffix.casefold())
        if media_type is None:
            raise SystemExit(f"Unsupported DATA-31 source: {source_path.suffix}")
        result = service.process(
            DocumentSource(
                document_id=f"pdf001h-{record['caseId']}",
                filename=source_path.name,
                content=source_path.read_bytes(),
                declared_media_type=media_type,
                source_reference=f"pdf001h-{record['caseId']}",
            )
        ).public_dict()
        expected_type = DOCUMENT_TYPE_BY_CATEGORY[category]
        if result["documentType"] != expected_type:
            raise SystemExit(f"Template family drift for {record['caseId']}")
        data = result["data"]
        fields = {name: {"value": data.get(name)} for name in FIELD_SPECS[category]}
        if category == "contract":
            fields.update(
                {
                    name: {"value": data.get(name)}
                    for name in ("professional_title", "role_title")
                }
            )
        processing = result["processing"]
        documents.append(
            {
                "caseId": record["caseId"],
                "category": category,
                "sourceFormat": record["sourceFormat"],
                "sourceFile": source_path.name,
                "sourceSha256": record["sourceSha256"],
                "predictedCategory": category,
                "fields": fields,
                "evaluationIncluded": True,
                "processing": {
                    "usesOcr": processing["usesOcr"],
                    "ocrEngine": processing.get("ocrEngine"),
                    "ocrScope": "OCR_ALLOWED" if processing["usesOcr"] else "NATIVE_ONLY",
                    "recommendedAction": result["quality"]["recommendedAction"],
                    "parserId": result["templateParserId"],
                    "parserVersion": result["templateParserVersion"],
                    "templateVersion": result["templateVersion"],
                    "schemaVersion": result.get("schemaVersion"),
                },
            }
        )
    return {
        "schemaVersion": PREDICTION_SCHEMA,
        "datasetId": inventory["dataset"]["datasetId"],
        "datasetDigest": inventory["dataset"]["contentDigest"],
        "documentCount": len(documents),
        "runtimeProfile": "template-first",
        "ocrBackend": ocr_backend,
                    "parserId": STRUCTURED_HR_PARSER_ID,
                    "parserVersion": STRUCTURED_HR_PARSER_VERSION,
        "ocrScopePolicy": "all-active-families",
        "containsRealPII": True,
        "localOnly": True,
        "predictionBlindDuringGroundTruthReview": True,
        "documents": documents,
    }


def _summary(
    prediction: dict[str, Any],
    aggregate: dict[str, Any],
    ground_truth: dict[str, Any],
    prediction_path: Path,
    report_path: Path,
    *,
    field_scope: Mapping[str, tuple[str, ...]] | None = None,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contracts = [item for item in prediction["documents"] if item["category"] == "contract"]
    truth_by_id = {str(item["caseId"]): item for item in ground_truth["cases"]}
    contract23 = next(item for item in contracts if item["caseId"] == "contract-004")
    professional = contract23["fields"]["professional_title"]["value"]
    historical = next(
        item["value"]
        for item in truth_by_id["contract-004"]["fields"]
        if item["name"] == "job_title"
    )
    metrics = aggregate["metrics"]
    active_field_count = aggregate["fieldCount"]
    scope_aware = coverage is not None
    required_strict = (
        math.ceil(active_field_count * STRICT_GATE_EXACT / STRICT_GATE_FIELDS)
        if scope_aware
        else STRICT_GATE_EXACT
    )
    required_accepted = active_field_count if scope_aware else STRICT_GATE_FIELDS
    return {
        "schemaVersion": SUMMARY_SCHEMA,
        "datasetId": "DATA-31",
        "runtime": {
            "runtimeProfile": "template-first",
        "parserId": STRUCTURED_HR_PARSER_ID,
        "parserVersion": STRUCTURED_HR_PARSER_VERSION,
            "contractTemplateVersion": "2.1",
            "contractSchemaVersion": "2.1.0",
            "titlePolicy": (
                "professional_title+role_title; "
                "job_title=role_title-or-professional_title"
            ),
            "matchingPolicy": MATCHING_POLICY_V2,
        },
        "scope": {
            "documents": len(prediction["documents"]),
            "fields": active_field_count,
            "activeFieldCount": active_field_count,
            "outOfScopeFieldCount": coverage["outOfScopeFieldCount"] if coverage else 0,
            "coverageDecisionStatus": coverage["status"] if coverage else "NOT_APPLIED",
            "groundTruthOverrideFieldCount": (
                coverage["groundTruthOverrideFieldCount"] if coverage else 0
            ),
            "contractDocuments": len(contracts),
            "cvDocuments": sum(item["category"] == "cv" for item in prediction["documents"]),
            "ieltsDocuments": sum(item["category"] == "ielts" for item in prediction["documents"]),
        },
        "groundTruthCoverage": _ground_truth_coverage(
            prediction, ground_truth, field_scope=field_scope
        ),
        "metrics": metrics,
        "qualityGate": {
            "scopeAware": scope_aware,
            "requiredStrictExact": required_strict,
            "requiredAccepted": required_accepted,
            "strictPass": metrics["fieldExactMatchCount"] >= required_strict,
            "acceptedPass": metrics["fieldAcceptedMatchCount"] >= required_accepted,
            "decision": "PASS"
            if metrics["fieldExactMatchCount"] >= required_strict
            and metrics["fieldAcceptedMatchCount"] >= required_accepted
            else "HOLD",
        },
        "titleSchema": {
            "professionalTitlePresentCount": sum(
                item["fields"]["professional_title"]["value"] is not None
                for item in contracts
            ),
            "roleTitlePresentCount": sum(
                item["fields"]["role_title"]["value"] is not None for item in contracts
            ),
            "jobTitleMapsToRoleTitleCount": sum(
                item["fields"]["job_title"]["value"] == item["fields"]["role_title"]["value"]
                for item in contracts
            ),
            "contract23ProfessionalHistoricalParity": professional == historical,
        },
        "safety": {
            "schemaErrors": aggregate["schemaErrors"],
            "containsRawFieldValues": False,
            "containsRawOcrText": False,
            "containsSourcePaths": False,
            "promotionAllowed": False,
            "groundTruthRewritten": False,
            "coverageOverlayApplied": scope_aware,
            "groundTruthOverrideApplied": bool(
                coverage and coverage["groundTruthOverrideFieldCount"]
            ),
            "predictionSha256": _sha256(prediction_path),
            "aggregateReportSha256": _sha256(report_path),
        },
    }


def _ground_truth_coverage(
    prediction: dict[str, Any],
    ground_truth: dict[str, Any],
    *,
    field_scope: Mapping[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    truth_by_id = {str(item["caseId"]): item for item in ground_truth["cases"]}
    totals = {"fields": 0, "populated": 0, "empty": 0, "predictionForEmpty": 0, "bothEmpty": 0}
    by_category: dict[str, dict[str, int]] = {}
    for document in prediction["documents"]:
        category = str(document["category"])
        stats = by_category.setdefault(category, {key: 0 for key in totals})
        truth = {
            str(item["name"]): item.get("value")
            for item in truth_by_id[str(document["caseId"])]["fields"]
        }
        case_id = str(document["caseId"])
        names = tuple(
            name
            for name in FIELD_SPECS[category]
            if field_scope is None or name in field_scope.get(case_id, FIELD_SPECS[category])
        )
        for name in names:
            truth_present = truth.get(name) not in (None, "")
            prediction_present = document["fields"].get(name, {}).get("value") not in (None, "")
            key = "populated" if truth_present else "empty"
            stats["fields"] += 1
            stats[key] += 1
            totals["fields"] += 1
            totals[key] += 1
            if not truth_present and prediction_present:
                stats["predictionForEmpty"] += 1
                totals["predictionForEmpty"] += 1
            if not truth_present and not prediction_present:
                stats["bothEmpty"] += 1
                totals["bothEmpty"] += 1
    return {"total": totals, "byCategory": by_category}


def build_data31_coverage_scope(
    inventory: dict[str, Any],
    ground_truth: dict[str, Any],
    coverage_decision: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, tuple[str, ...]] | None, dict[str, Any] | None]:
    """Apply private coverage and scope overlays without rewriting Ground Truth."""
    if coverage_decision is None:
        return ground_truth, None, None
    if coverage_decision.get("schemaVersion") != "data31-ground-truth-coverage-decision/1.0.0":
        raise ValueError("DATA-31 coverage decision schema is invalid")
    if coverage_decision.get("datasetId") != inventory["dataset"]["datasetId"]:
        raise ValueError("DATA-31 coverage decision dataset mismatch")
    decisions = coverage_decision.get("cases")
    if not isinstance(decisions, dict):
        raise ValueError("DATA-31 coverage decision cases are invalid")
    scope_overrides = coverage_decision.get("scopeOverrides", {})
    if not isinstance(scope_overrides, dict):
        raise ValueError("DATA-31 scope overrides are invalid")
    ground_truth_overrides = coverage_decision.get("groundTruthOverrides", {})
    if not isinstance(ground_truth_overrides, dict):
        raise ValueError("DATA-31 Ground Truth overrides are invalid")
    inventory_by_id = {str(item["caseId"]): item for item in inventory["cases"]}
    truth_by_id = {str(item["caseId"]): item for item in ground_truth.get("cases", [])}
    if set(decisions).difference(inventory_by_id):
        raise ValueError("DATA-31 coverage decision contains an unknown case")
    if set(scope_overrides).difference(inventory_by_id) or set(ground_truth_overrides).difference(
        inventory_by_id
    ):
        raise ValueError("DATA-31 coverage overlay contains an unknown case")
    effective = copy.deepcopy(ground_truth)
    effective_by_id = {str(item["caseId"]): item for item in effective.get("cases", [])}
    field_scope: dict[str, tuple[str, ...]] = {}
    out_of_scope = 0
    scope_override_count = 0
    ground_truth_override_count = 0
    missing_total = 0
    decided_total = 0
    for case_id, record in inventory_by_id.items():
        category = str(record["category"])
        expected = FIELD_SPECS[category]
        truth_case = truth_by_id.get(case_id)
        effective_case = effective_by_id.get(case_id)
        if truth_case is None or effective_case is None:
            raise ValueError(f"DATA-31 Ground Truth case is missing: {case_id}")
        truth_fields = {str(item["name"]): item for item in truth_case.get("fields", [])}
        effective_fields = {str(item["name"]): item for item in effective_case.get("fields", [])}
        if set(expected).difference(truth_fields) or set(expected).difference(effective_fields):
            raise ValueError(f"DATA-31 Ground Truth field schema is incomplete: {case_id}")
        missing = {
            name for name in expected if truth_fields.get(name, {}).get("value") in (None, "")
        }
        ground_truth_override = ground_truth_overrides.get(case_id)
        if ground_truth_override is not None:
            if not isinstance(ground_truth_override, dict):
                raise ValueError(f"DATA-31 Ground Truth override is invalid: {case_id}")
            if ground_truth_override.get("category") != category:
                raise ValueError(f"DATA-31 Ground Truth override category mismatch: {case_id}")
            if ground_truth_override.get("sourceSha256") != record.get("sourceSha256"):
                raise ValueError(f"DATA-31 Ground Truth override source mismatch: {case_id}")
            override_fields = ground_truth_override.get("fields")
            if not isinstance(override_fields, dict) or not set(override_fields).issubset(
                set(expected)
            ) or set(override_fields) & missing:
                raise ValueError(f"DATA-31 Ground Truth override field set is invalid: {case_id}")
            for name, override in override_fields.items():
                value = override.get("value") if isinstance(override, dict) else None
                if (
                    not isinstance(override, dict)
                    or override.get("disposition") != "GROUND_TRUTH"
                    or not isinstance(value, str)
                    or not value.strip()
                ):
                    raise ValueError(
                        f"DATA-31 Ground Truth override must contain a value: {case_id}.{name}"
                    )
                effective_fields[name]["value"] = " ".join(value.split()).strip()
                ground_truth_override_count += 1
        override_record = scope_overrides.get(case_id)
        override_names: set[str] = set()
        if override_record is not None:
            if not isinstance(override_record, dict):
                raise ValueError(f"DATA-31 scope override is invalid: {case_id}")
            if override_record.get("category") != category:
                raise ValueError(f"DATA-31 scope override category mismatch: {case_id}")
            if override_record.get("sourceSha256") != record.get("sourceSha256"):
                raise ValueError(f"DATA-31 scope override source mismatch: {case_id}")
            override_fields = override_record.get("fields")
            if not isinstance(override_fields, dict):
                raise ValueError(f"DATA-31 scope override fields are invalid: {case_id}")
            override_names = set(override_fields)
            if not override_names.issubset(set(expected)) or override_names & missing:
                raise ValueError(f"DATA-31 scope override field set is invalid: {case_id}")
            for name, override in override_fields.items():
                if (
                    not isinstance(override, dict)
                    or override.get("disposition") != "OUT_OF_SCOPE"
                    or override.get("value") not in (None, "")
                ):
                    raise ValueError(
                        f"DATA-31 scope override must be OUT_OF_SCOPE: {case_id}.{name}"
                    )
                override_names.add(name)
            out_of_scope += len(override_names)
            scope_override_count += len(override_names)
        missing_total += len(missing)
        case_decision = decisions.get(case_id)
        if missing and not isinstance(case_decision, dict):
            raise ValueError(f"DATA-31 coverage decision is incomplete: {case_id}")
        if not missing and case_decision is not None:
            raise ValueError(f"DATA-31 coverage decision has an unexpected case: {case_id}")
        if not missing:
            field_scope[case_id] = tuple(name for name in expected if name not in override_names)
            continue
        if not isinstance(case_decision, dict):
            raise ValueError(f"DATA-31 coverage decision is incomplete: {case_id}")
        decision_record: dict[str, Any] = case_decision
        if decision_record.get("category") != category:
            raise ValueError(f"DATA-31 coverage category mismatch: {case_id}")
        if decision_record.get("sourceSha256") != record.get("sourceSha256"):
            raise ValueError(f"DATA-31 coverage source mismatch: {case_id}")
        case_fields = decision_record.get("fields")
        if not isinstance(case_fields, dict) or set(case_fields) != missing:
            raise ValueError(f"DATA-31 coverage fields are incomplete: {case_id}")
        active = []
        for name in expected:
            if name not in missing:
                active.append(name)
                continue
            decision = case_fields[name]
            if not isinstance(decision, dict):
                raise ValueError(f"DATA-31 coverage field decision is invalid: {case_id}.{name}")
            disposition = decision.get("disposition")
            value = decision.get("value")
            if disposition == "GROUND_TRUTH":
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"DATA-31 Ground Truth is empty: {case_id}.{name}")
                effective_fields[name]["value"] = " ".join(value.split()).strip()
                active.append(name)
            elif disposition == "OUT_OF_SCOPE":
                if value not in (None, ""):
                    raise ValueError(f"DATA-31 OUT_OF_SCOPE has a value: {case_id}.{name}")
                out_of_scope += 1
            else:
                raise ValueError(f"DATA-31 coverage disposition is invalid: {case_id}.{name}")
            decided_total += 1
        field_scope[case_id] = tuple(name for name in active if name not in override_names)
    if coverage_decision.get("status") != "COMPLETE" or decided_total != missing_total:
        raise ValueError("DATA-31 coverage decision is not complete")
    active_count = sum(len(names) for names in field_scope.values())
    return effective, field_scope, {
        "status": "COMPLETE",
        "missingFieldCount": missing_total,
        "decidedFieldCount": decided_total,
        "activeFieldCount": active_count,
        "outOfScopeFieldCount": out_of_scope,
        "scopeOverrideFieldCount": scope_override_count,
        "groundTruthOverrideFieldCount": ground_truth_override_count,
    }


def _new_private_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if any((parent / ".git").exists() for parent in (resolved.parent, *resolved.parent.parents)):
        raise SystemExit("Private DATA-31 artifact must stay outside Git")
    if resolved.exists():
        raise SystemExit(f"Refusing to overwrite private artifact: {resolved.name}")
    return resolved


def _read_private_json(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    if any((parent / ".git").exists() for parent in (resolved.parent, *resolved.parent.parents)):
        raise SystemExit("Private DATA-31 coverage decision must stay outside Git")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("DATA-31 coverage decision must be a JSON object")
    return payload


def _write_private(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
