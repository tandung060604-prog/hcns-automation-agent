"""Deterministic baseline DocumentType classifier."""

from __future__ import annotations

from dataclasses import dataclass

from hcns_agent.adapters.text_normalization import normalize_text
from hcns_agent.domain.canonical import CanonicalDocument, SourceLocation
from hcns_agent.domain.content import iter_text_observations
from hcns_agent.domain.documents import DocumentType
from hcns_agent.domain.understanding import (
    ClassificationCandidate,
    DocumentClassification,
)


@dataclass(frozen=True, slots=True)
class _Marker:
    text: str
    weight: float


_RULES: dict[DocumentType, tuple[_Marker, ...]] = {
    DocumentType.CV: (
        _Marker("curriculum vitae", 3.0),
        _Marker("cv", 2.0),
        _Marker("ky nang", 1.0),
        _Marker("kinh nghiem", 1.0),
        _Marker("hoc van", 1.0),
    ),
    DocumentType.EMPLOYMENT_CONTRACT: (
        _Marker("hop dong lao dong", 3.0),
        _Marker("employment contract", 3.0),
        _Marker("hop dong thu viec", 3.0),
        _Marker("thu viec", 3.0),
        _Marker("probation", 2.5),
        _Marker("hop dong", 1.5),
        _Marker("dieu khoan", 1.0),
        _Marker("so hop dong", 1.0),
    ),
    DocumentType.CERTIFICATE: (
        _Marker("ielts", 4.0),
        _Marker("test report form", 4.0),
        _Marker("overall band score", 3.0),
        _Marker("candidate number", 2.0),
    ),
    DocumentType.LEAVE_REQUEST: (
        _Marker("don nghi phep", 3.0),
        _Marker("leave request", 3.0),
        _Marker("nghi phep", 2.0),
        _Marker("ly do nghi", 1.0),
    ),
    DocumentType.ADMINISTRATIVE_FORM: (
        _Marker("bieu mau hanh chinh", 3.0),
        _Marker("administrative form", 3.0),
        _Marker("bieu mau", 1.0),
    ),
}


class RuleBasedDocumentClassifier:
    name = "document-type/rule-baseline"
    version = "1.0.0"

    def __init__(self, *, minimum_confidence: float = 0.50) -> None:
        self._minimum_confidence = minimum_confidence

    def classify(self, document: CanonicalDocument) -> DocumentClassification:
        observations = tuple(iter_text_observations(document))
        normalized = tuple(
            (observation, normalize_text(observation.text)) for observation in observations
        )
        candidates: list[ClassificationCandidate] = []
        evidence_by_type: dict[DocumentType, tuple[SourceLocation, ...]] = {}

        for document_type, markers in _RULES.items():
            matched_markers: list[str] = []
            evidence: list[SourceLocation] = []
            score = 0.0
            for marker in markers:
                marker_text = normalize_text(marker.text)
                matches = [
                    observation
                    for observation, text in normalized
                    if marker_text and _marker_matches(marker_text, text)
                ]
                if not matches:
                    continue
                matched_markers.append(marker.text)
                score += marker.weight
                for observation in matches:
                    if observation.source not in evidence:
                        evidence.append(observation.source)
            if score <= 0:
                continue
            confidence = min(0.99, score / (score + 1.5))
            candidates.append(
                ClassificationCandidate(
                    document_type=document_type,
                    confidence=confidence,
                    matched_markers=tuple(matched_markers),
                )
            )
            evidence_by_type[document_type] = tuple(evidence)

        candidates.sort(
            key=lambda candidate: (-candidate.confidence, candidate.document_type.value)
        )
        if not candidates or candidates[0].confidence < self._minimum_confidence:
            best_confidence = candidates[0].confidence if candidates else 0.0
            return DocumentClassification(
                document_type=DocumentType.UNKNOWN,
                confidence=max(0.0, 1.0 - best_confidence),
                candidates=tuple(candidates),
                evidence=(),
                classifier_name=self.name,
                classifier_version=self.version,
            )

        best = candidates[0]
        return DocumentClassification(
            document_type=best.document_type,
            confidence=best.confidence,
            candidates=tuple(candidates),
            evidence=evidence_by_type[best.document_type],
            classifier_name=self.name,
            classifier_version=self.version,
        )


def _marker_matches(marker: str, text: str) -> bool:
    if " " not in marker and len(marker) <= 3:
        return marker in text.split()
    return marker in text
