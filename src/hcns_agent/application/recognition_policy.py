"""Versioned OCR selection policies.

Policies are immutable evidence. A shadow policy may expose an alternative
candidate for human review but cannot silently replace the selected text.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from hcns_agent.application.ocr_metrics import (
    METRIC_SPEC_VERSION,
    normalize_for_evaluation,
)

SHADOW_REVIEW_ONLY = "SHADOW_REVIEW_ONLY"


@dataclass(frozen=True, slots=True)
class RecognitionPolicy:
    policy_id: str
    version: str
    mode: str
    metric_spec_version: str
    crop_profile: str
    primary_profile: str
    review_candidate_profiles: tuple[str, ...]
    primary_confidence_review_threshold: float | None
    maximum_baseline_correct_losses: int
    auto_replace_selected_text: bool

    def __post_init__(self) -> None:
        for value, name in (
            (self.policy_id, "policy_id"),
            (self.version, "version"),
            (self.metric_spec_version, "metric_spec_version"),
            (self.crop_profile, "crop_profile"),
            (self.primary_profile, "primary_profile"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not self.review_candidate_profiles:
            raise ValueError("review_candidate_profiles must not be empty")
        if (
            self.primary_confidence_review_threshold is not None
            and not 0.0 <= self.primary_confidence_review_threshold <= 1.0
        ):
            raise ValueError(
                "primary_confidence_review_threshold must be between 0 and 1"
            )
        if self.maximum_baseline_correct_losses < 0:
            raise ValueError("maximum_baseline_correct_losses must not be negative")
        if self.mode == SHADOW_REVIEW_ONLY and self.auto_replace_selected_text:
            raise ValueError("Shadow policies cannot auto-replace selected text")

    def manifest(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "policyId": self.policy_id,
            "version": self.version,
            "mode": self.mode,
            "metricSpecVersion": self.metric_spec_version,
            "cropProfile": self.crop_profile,
            "primaryProfile": self.primary_profile,
            "reviewCandidateProfiles": list(self.review_candidate_profiles),
            "primaryConfidenceReviewThreshold": (
                self.primary_confidence_review_threshold
            ),
            "maximumBaselineCorrectLosses": self.maximum_baseline_correct_losses,
            "autoReplaceSelectedText": self.auto_replace_selected_text,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        payload["policyDigest"] = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
        return payload

    def selected_text(self, baseline: str, review_candidate: str | None = None) -> str:
        if self.auto_replace_selected_text and review_candidate:
            return review_candidate
        return baseline


PADDLE_VERIFICATION_POLICY_V1 = RecognitionPolicy(
    policy_id="paddle-independent-verification",
    version="1.0.0",
    mode=SHADOW_REVIEW_ONLY,
    metric_spec_version=METRIC_SPEC_VERSION,
    crop_profile="detector_bbox",
    primary_profile="paddle_detector_raw",
    review_candidate_profiles=("easyocr_vi", "vietocr_vgg_seq2seq"),
    primary_confidence_review_threshold=None,
    maximum_baseline_correct_losses=0,
    auto_replace_selected_text=False,
)


PHASE14_6_SHADOW_POLICY = RecognitionPolicy(
    policy_id="phase14.6-vietocr-conditional-review",
    version="1.0.0",
    mode=SHADOW_REVIEW_ONLY,
    metric_spec_version=METRIC_SPEC_VERSION,
    crop_profile="bbox_balanced_64",
    primary_profile="vietocr_vgg_seq2seq",
    review_candidate_profiles=(
        "vietocr_vgg_transformer",
        "paddle_detector_raw",
    ),
    primary_confidence_review_threshold=0.4,
    maximum_baseline_correct_losses=0,
    auto_replace_selected_text=False,
)


@dataclass(frozen=True, slots=True)
class VerifierDecision:
    selected_text: str
    selected_confidence: float
    verifier_text: str
    status: str
    exact_agreement: bool
    rule: str


@dataclass(frozen=True, slots=True)
class VerifierRecognitionPolicy:
    """A primary-preserving policy with one independent verifier."""

    policy_id: str
    version: str
    metric_spec_version: str
    crop_profile: str
    primary_profile: str
    verifier_profile: str
    detector_profile: str
    mode: str = SHADOW_REVIEW_ONLY
    auto_replace_selected_text: bool = False

    def __post_init__(self) -> None:
        required = (
            self.policy_id,
            self.version,
            self.metric_spec_version,
            self.crop_profile,
            self.primary_profile,
            self.verifier_profile,
            self.detector_profile,
        )
        if any(not value.strip() for value in required):
            raise ValueError("Verifier policy identifiers must not be empty")
        if self.primary_profile == self.verifier_profile:
            raise ValueError("Primary and verifier profiles must be independent")
        if self.detector_profile in {
            self.primary_profile,
            self.verifier_profile,
        }:
            raise ValueError("Detector evidence must not be a recognizer profile")
        if self.mode == SHADOW_REVIEW_ONLY and self.auto_replace_selected_text:
            raise ValueError("Shadow verifier policy cannot auto-replace text")

    def decide(
        self,
        *,
        primary_text: str,
        primary_confidence: float,
        verifier_text: str,
    ) -> VerifierDecision:
        primary = normalize_for_evaluation(primary_text)
        verifier = normalize_for_evaluation(verifier_text)
        agreement = bool(primary) and primary == verifier
        return VerifierDecision(
            selected_text=primary,
            selected_confidence=max(0.0, min(1.0, float(primary_confidence))),
            verifier_text=verifier,
            status="verified" if agreement else "needs_review",
            exact_agreement=agreement,
            rule=(
                "primary_preserved_transformer_exact_agreement"
                if agreement
                else "primary_preserved_transformer_disagreement_review"
            ),
        )

    def manifest(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "policyId": self.policy_id,
            "version": self.version,
            "mode": self.mode,
            "metricSpecVersion": self.metric_spec_version,
            "cropProfile": self.crop_profile,
            "primaryProfile": self.primary_profile,
            "verifierProfile": self.verifier_profile,
            "detectorEvidenceProfile": self.detector_profile,
            "selectionExcludedProfiles": [self.detector_profile],
            "agreementRule": "strict_nfc_whitespace_case_sensitive",
            "agreementAction": "mark_verified_evidence_only",
            "disagreementAction": "preserve_primary_and_require_review",
            "autoReplaceSelectedText": self.auto_replace_selected_text,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        payload["policyDigest"] = f"sha256:{hashlib.sha256(canonical).hexdigest()}"
        return payload


PHASE14_8_TRANSFORMER_VERIFIER_POLICY = VerifierRecognitionPolicy(
    policy_id="phase14.8-seq2seq-transformer-verifier",
    version="1.0.0",
    metric_spec_version=METRIC_SPEC_VERSION,
    crop_profile="bbox_balanced_64",
    primary_profile="vietocr_vgg_seq2seq",
    verifier_profile="vietocr_vgg_transformer",
    detector_profile="paddle_detector_raw",
)
