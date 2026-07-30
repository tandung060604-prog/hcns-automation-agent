import unittest

from apps.ocr_lab.api.document_route_safety import (
    safe_existing_document_route,
    selected_orientations_are_identity,
)


class Phase11RouteSafetyTests(unittest.TestCase):
    def test_rejected_rotation_cannot_route_a_cv_as_identity(self) -> None:
        pages = [
            {
                "identityLikely": True,
                "selectedIdentityLikely": False,
                "candidates": [
                    {
                        "rotationDegrees": 180,
                        "identityAnchorHits": ["ngay sinh"],
                        "identityNumberCandidateCount": 1,
                    }
                ],
            }
        ]
        self.assertFalse(selected_orientations_are_identity(pages))

    def test_selected_identity_page_can_route_to_cccd_parser(self) -> None:
        self.assertTrue(
            selected_orientations_are_identity(
                [{"selectedIdentityLikely": True}]
            )
        )

    def test_mixed_multi_page_document_does_not_route_wholly_as_cccd(
        self,
    ) -> None:
        self.assertFalse(
            selected_orientations_are_identity(
                [
                    {"selectedIdentityLikely": True},
                    {"selectedIdentityLikely": False},
                ]
            )
        )

    def test_strong_cv_markers_drop_a_stale_identity_route(self) -> None:
        route = safe_existing_document_route(
            "IDENTITY_DOCUMENT",
            "HỌC VẤN\nKINH NGHIỆM\nKỸ NĂNG\nPortfolio",
        )
        self.assertIsNone(route)

    def test_identity_route_is_preserved_without_cv_sections(self) -> None:
        route = safe_existing_document_route(
            "IDENTITY_DOCUMENT",
            "CĂN CƯỚC CÔNG DÂN\nHọ và tên\nNgày sinh",
        )
        self.assertEqual("IDENTITY_DOCUMENT", route)
