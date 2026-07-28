from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.validate_phase14_6_lock import (
    load_and_validate_lock,
    verify_local_models,
)


class Phase146LockTests(unittest.TestCase):
    def test_checked_in_lock_matches_code_and_protocol(self) -> None:
        root = Path(__file__).resolve().parents[1]

        payload = load_and_validate_lock(
            root / "config" / "phase14_6_benchmark_lock.json"
        )

        self.assertFalse(payload["policy"]["autoReplaceSelectedText"])
        self.assertFalse(payload["heldOutProtocol"]["thresholdRetuningAllowed"])
        self.assertGreaterEqual(
            payload["heldOutProtocol"]["minimumDocumentCount"],
            15,
        )

    def test_model_verifier_rejects_a_changed_weight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            model = root / "model.pth"
            model.write_bytes(b"locked synthetic model")
            payload = {
                "models": [
                    {
                        "profile": "synthetic",
                        "root": "privateRuntime",
                        "relativePath": "model.pth",
                        "bytes": model.stat().st_size,
                        "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                    }
                ]
            }
            verify_local_models(payload, {"privateRuntime": root})
            model.write_bytes(b"changed synthetic model")

            with self.assertRaisesRegex(ValueError, "size changed|hash changed"):
                verify_local_models(payload, {"privateRuntime": root})


if __name__ == "__main__":
    unittest.main()
