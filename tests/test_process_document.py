from unittest import TestCase

from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.application.process_document import ProcessDocument
from hcns_agent.domain.models import DocumentType, HrDocument


class ProcessDocumentTests(TestCase):
    def test_sensitive_document_is_routed_to_human_review(self) -> None:
        document = HrDocument(
            document_id="SYNTHETIC-ID-0001",
            filename="synthetic.png",
            document_type=DocumentType.IDENTITY_CARD,
        )

        proposal = ProcessDocument(DeterministicMockOcrEngine()).execute(document)

        self.assertTrue(proposal.requires_human_review)
        self.assertIn("requires review by policy", proposal.review_reasons[0])

    def test_low_confidence_output_is_not_accepted(self) -> None:
        document = HrDocument(
            document_id="SYNTHETIC-CV-0001",
            filename="synthetic.png",
            document_type=DocumentType.CV,
        )

        proposal = ProcessDocument(DeterministicMockOcrEngine(confidence=0.42)).execute(document)

        self.assertTrue(proposal.requires_human_review)
        self.assertEqual(1, len(proposal.fields))
        self.assertEqual("NEEDS_REVIEW", proposal.fields[0].status.value)
        self.assertTrue(
            any("below the confidence threshold" in reason for reason in proposal.review_reasons)
        )

    def test_high_confidence_non_sensitive_demo_can_be_proposed(self) -> None:
        document = HrDocument(
            document_id="SYNTHETIC-CV-0002",
            filename="synthetic.png",
            document_type=DocumentType.CV,
        )

        proposal = ProcessDocument(DeterministicMockOcrEngine()).execute(document)

        self.assertTrue(proposal.requires_human_review)
        self.assertEqual(1, len(proposal.fields))
        self.assertEqual("ACCEPTED", proposal.fields[0].status.value)
        self.assertIn("DocumentType.CV requires review by policy", proposal.review_reasons)
