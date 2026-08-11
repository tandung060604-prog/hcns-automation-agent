from __future__ import annotations

import unittest

from scripts.run_m5_cam_006_api_bridge_smoke import run_smoke


class M5Cam006ApiBridgeSmokeTests(unittest.TestCase):
    def test_is_read_only_and_stops_at_phase15_bridge(self) -> None:
        report = run_smoke()

        self.assertTrue(report["passed"])
        self.assertEqual(report["fixtureCount"], 2)
        self.assertEqual(report["getRequestCount"], 2)
        self.assertEqual(report["postRequestCount"], 0)
        self.assertEqual(report["httpMethodPolicy"], "GET_ONLY")
        self.assertEqual(report["phase15BridgeProjectionCount"], 2)
        self.assertEqual(report["manualReviewCount"], 2)
        self.assertEqual(report["autoContinueCount"], 0)
        self.assertTrue(report["scalarOnly"])
        self.assertTrue(report["opaqueReferenceOnly"])
        self.assertEqual(report["schemaWhitelistErrorCount"], 0)
        self.assertEqual(report["nonScalarValueCount"], 0)
        self.assertEqual(report["sourceMutationCount"], 0)
        self.assertEqual(report["camundaProcessStartAttempts"], 0)
        self.assertEqual(report["hrisSideEffectCount"], 0)
        self.assertEqual(report["notificationSideEffectCount"], 0)
        self.assertFalse(report["groundTruthUsed"])
        self.assertFalse(report["evaluateOnceArtifactTouched"])
        self.assertFalse(report["realCohortOpened"])
        self.assertFalse(report["promotionAllowed"])
