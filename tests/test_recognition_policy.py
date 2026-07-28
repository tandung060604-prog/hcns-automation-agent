from __future__ import annotations

import unittest

from hcns_agent.application.ocr_metrics import METRIC_SPEC_VERSION
from hcns_agent.application.recognition_policy import (
    PHASE14_6_SHADOW_POLICY,
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


if __name__ == "__main__":
    unittest.main()
