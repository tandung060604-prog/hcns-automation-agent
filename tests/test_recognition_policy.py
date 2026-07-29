from __future__ import annotations

import json
import unittest
from pathlib import Path

from hcns_agent.application.ocr_metrics import METRIC_SPEC_VERSION
from hcns_agent.application.recognition_policy import (
    PHASE14_6_SHADOW_POLICY,
    PHASE14_8_TRANSFORMER_VERIFIER_POLICY,
    SHADOW_REVIEW_ONLY,
    RecognitionPolicy,
)


class RecognitionPolicyTests(unittest.TestCase):
    def test_phase14_6_policy_is_versioned_and_review_only(self) -> None:
        manifest = PHASE14_6_SHADOW_POLICY.manifest()

        self.assertEqual("1.0.0", manifest["version"])
        self.assertEqual(METRIC_SPEC_VERSION, manifest["metricSpecVersion"])
        self.assertEqual("bbox_balanced_64", manifest["cropProfile"])
        self.assertEqual(SHADOW_REVIEW_ONLY, manifest["mode"])
        self.assertEqual(0, manifest["maximumBaselineCorrectLosses"])
        self.assertFalse(manifest["autoReplaceSelectedText"])
        self.assertRegex(str(manifest["policyDigest"]), r"^sha256:[a-f0-9]{64}$")

    def test_shadow_policy_never_replaces_baseline_text(self) -> None:
        selected = PHASE14_6_SHADOW_POLICY.selected_text(
            "baseline",
            "review candidate",
        )

        self.assertEqual("baseline", selected)

    def test_shadow_policy_rejects_auto_replace_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot auto-replace"):
            RecognitionPolicy(
                policy_id="unsafe",
                version="1",
                mode=SHADOW_REVIEW_ONLY,
                metric_spec_version=METRIC_SPEC_VERSION,
                crop_profile="crop",
                primary_profile="primary",
                review_candidate_profiles=("candidate",),
                primary_confidence_review_threshold=0.8,
                maximum_baseline_correct_losses=0,
                auto_replace_selected_text=True,
            )

    def test_phase14_8_keeps_seq2seq_and_excludes_paddle_selection(self) -> None:
        policy = PHASE14_8_TRANSFORMER_VERIFIER_POLICY
        manifest = policy.manifest()

        decision = policy.decide(
            primary_text="NGUYỄN THỊ MAI",
            primary_confidence=0.82,
            verifier_text="NGUYỄN THỊ MAI",
        )

        self.assertEqual("NGUYỄN THỊ MAI", decision.selected_text)
        self.assertEqual("verified", decision.status)
        self.assertTrue(decision.exact_agreement)
        self.assertEqual(
            ["paddle_detector_raw"],
            manifest["selectionExcludedProfiles"],
        )
        self.assertFalse(manifest["autoReplaceSelectedText"])
        self.assertRegex(
            str(manifest["policyDigest"]),
            r"^sha256:[a-f0-9]{64}$",
        )

    def test_phase14_8_disagreement_preserves_primary_for_review(self) -> None:
        decision = PHASE14_8_TRANSFORMER_VERIFIER_POLICY.decide(
            primary_text="PHAM THI LINH",
            primary_confidence=0.77,
            verifier_text="PHẠM THỊ LINH",
        )

        self.assertEqual("PHAM THI LINH", decision.selected_text)
        self.assertEqual("needs_review", decision.status)
        self.assertFalse(decision.exact_agreement)

    def test_phase14_8_frozen_config_matches_code_policy(self) -> None:
        root = Path(__file__).resolve().parents[1]
        frozen = json.loads(
            (root / "config" / "phase14_8_recognition_policy.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            PHASE14_8_TRANSFORMER_VERIFIER_POLICY.manifest(),
            frozen["policy"],
        )
        paddle = next(
            model
            for model in frozen["models"]
            if model["profile"] == "paddle_detector_raw"
        )
        self.assertFalse(paddle["selectionEligible"])
        self.assertEqual(
            "DETECTOR_GEOMETRY_AND_AUDIT_EVIDENCE_ONLY",
            paddle["role"],
        )


if __name__ == "__main__":
    unittest.main()
