"""Deterministic baseline field extractors for initial HCNS document types."""

from __future__ import annotations

from dataclasses import dataclass

from hcns_agent.adapters.text_normalization import normalize_text
from hcns_agent.domain.canonical import CanonicalDocument, ScalarValue, SourceLocation
from hcns_agent.domain.content import TextObservation, iter_text_observations
from hcns_agent.domain.documents import DocumentType
from hcns_agent.domain.models import FieldStatus
from hcns_agent.domain.understanding import (
    BusinessField,
    DocumentClassification,
    FieldEvidence,
)


@dataclass(frozen=True, slots=True)
class _FieldSpec:
    name: str
    aliases: tuple[str, ...]
    sensitive: bool = False


class _LabeledFieldExtractor:
    name = "field/labeled-baseline"
    version = "1.0.0"
    document_types: frozenset[DocumentType] = frozenset()
    field_specs: tuple[_FieldSpec, ...] = ()

    def supports(self, document_type: DocumentType) -> bool:
        return document_type in self.document_types

    def extract(
        self,
        document: CanonicalDocument,
        classification: DocumentClassification,
    ) -> tuple[BusinessField, ...]:
        if not self.supports(classification.document_type):
            return ()
        observations = tuple(iter_text_observations(document))
        extracted: list[BusinessField] = []
        for spec in self.field_specs:
            extracted.extend(self._extract_spec(observations, spec))
        return tuple(extracted)

    def _extract_spec(
        self,
        observations: tuple[TextObservation, ...],
        spec: _FieldSpec,
    ) -> tuple[BusinessField, ...]:
        aliases = tuple(normalize_text(alias) for alias in spec.aliases)
        fields: list[BusinessField] = []
        for observation in observations:
            labeled_value = _split_labeled_value(observation.text)
            if labeled_value is None:
                continue
            label, value = labeled_value
            normalized_label = normalize_text(label)
            if not any(
                normalized_label == alias or normalized_label.endswith(f" {alias}")
                for alias in aliases
            ):
                continue
            fields.append(
                self._field(
                    name=spec.name,
                    value=value,
                    confidence=0.96,
                    sensitive=spec.sensitive,
                    source=observation.source,
                    method="explicit-label",
                )
            )
        return tuple(fields)

    def _field(
        self,
        *,
        name: str,
        value: ScalarValue,
        confidence: float,
        sensitive: bool,
        source: SourceLocation,
        method: str,
    ) -> BusinessField:
        return BusinessField(
            name=name,
            value=value,
            confidence=confidence,
            status=FieldStatus.ACCEPTED,
            sensitive=sensitive,
            evidence=(FieldEvidence(source=source, method=method),),
            extractor_name=self.name,
            extractor_version=self.version,
        )


class CvFieldExtractor(_LabeledFieldExtractor):
    name = "field/cv-labeled"
    document_types = frozenset({DocumentType.CV})
    field_specs = (
        _FieldSpec("full_name", ("họ tên", "ho ten", "full name"), sensitive=True),
        _FieldSpec("skills", ("kỹ năng", "ky nang", "skills")),
        _FieldSpec("education", ("học vấn", "hoc van", "education")),
    )


class EmploymentContractFieldExtractor(_LabeledFieldExtractor):
    name = "field/employment-contract-labeled"
    document_types = frozenset({DocumentType.EMPLOYMENT_CONTRACT})
    field_specs = (
        _FieldSpec("contract_number", ("số hợp đồng", "so hop dong", "contract number")),
        _FieldSpec(
            "employee_name",
            ("họ tên", "ho ten", "employee name", "người lao động"),
            sensitive=True,
        ),
        _FieldSpec("start_date", ("ngày bắt đầu", "ngay bat dau", "start date")),
        _FieldSpec("end_date", ("ngày kết thúc", "ngay ket thuc", "end date")),
        _FieldSpec("salary", ("lương", "luong", "salary"), sensitive=True),
    )


class LeaveRequestFieldExtractor(_LabeledFieldExtractor):
    name = "field/leave-request-labeled"
    document_types = frozenset({DocumentType.LEAVE_REQUEST})
    field_specs = (
        _FieldSpec(
            "employee_name",
            ("họ tên", "ho ten", "employee name"),
            sensitive=True,
        ),
        _FieldSpec("start_date", ("từ ngày", "tu ngay", "start date")),
        _FieldSpec("end_date", ("đến ngày", "den ngay", "end date")),
        _FieldSpec("reason", ("lý do", "ly do", "reason")),
    )


class TimesheetFieldExtractor(_LabeledFieldExtractor):
    name = "field/timesheet-native"
    document_types = frozenset({DocumentType.TIMESHEET})

    def extract(
        self,
        document: CanonicalDocument,
        classification: DocumentClassification,
    ) -> tuple[BusinessField, ...]:
        if not self.supports(classification.document_type) or document.content.workbook is None:
            return ()
        fields: list[BusinessField] = []
        for sheet in document.content.workbook.sheets:
            if not sheet.rows:
                continue
            header_cells = sheet.rows[0].cells
            headers = {cell.column_index: normalize_text(str(cell.value)) for cell in header_cells}
            employee_column = next(
                (
                    column
                    for column, header in headers.items()
                    if header in {"ma", "ma synthetic", "ma nhan vien", "employee code"}
                ),
                None,
            )
            formula_column = next(
                (
                    column
                    for column, header in headers.items()
                    if header in {"tong gio", "tonggio", "total hours"}
                ),
                None,
            )
            employee_values: list[str] = []
            employee_source: SourceLocation | None = None
            formulas: list[str] = []
            formula_source: SourceLocation | None = None
            for row in sheet.rows[1:]:
                if len(row.cells) < 2:
                    continue
                cells_by_column = {cell.column_index: cell for cell in row.cells}
                if employee_column is not None and employee_column in cells_by_column:
                    cell = cells_by_column[employee_column]
                    if cell.value is not None:
                        employee_values.append(str(cell.value))
                        employee_source = employee_source or cell.source
                if formula_column is not None and formula_column in cells_by_column:
                    cell = cells_by_column[formula_column]
                    if cell.formula:
                        formulas.append(cell.formula)
                        formula_source = formula_source or cell.source
            if employee_values and employee_source is not None:
                fields.append(
                    self._field(
                        name="employee_codes",
                        value=",".join(employee_values),
                        confidence=0.93,
                        sensitive=False,
                        source=employee_source,
                        method="native-sheet-column",
                    )
                )
                fields.append(
                    self._field(
                        name="entry_count",
                        value=len(employee_values),
                        confidence=0.99,
                        sensitive=False,
                        source=employee_source,
                        method="native-row-count",
                    )
                )
            if formulas and formula_source is not None:
                fields.append(
                    self._field(
                        name="total_hours_formulas",
                        value=";".join(formulas),
                        confidence=0.99,
                        sensitive=False,
                        source=formula_source,
                        method="native-formula",
                    )
                )
        return tuple(fields)


def _split_labeled_value(text: str) -> tuple[str, str] | None:
    for separator in (":", "："):
        if separator in text:
            label, value = text.split(separator, maxsplit=1)
            if label.strip() and value.strip():
                return label.strip(), value.strip()
    return None
