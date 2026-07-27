from unittest import TestCase

from hcns_agent.domain.workflow import WorkflowCase, WorkflowEvent, WorkflowState


class WorkflowCaseTests(TestCase):
    def test_approved_case_reaches_ready_to_sync(self) -> None:
        case = WorkflowCase(case_id="CASE-SYNTHETIC-001")
        case = case.transition(WorkflowEvent.OCR_SUCCEEDED, actor_id="ocr-worker")
        case = case.transition(WorkflowEvent.REQUEST_REVIEW, actor_id="policy-engine")
        case = case.transition(WorkflowEvent.APPROVE, actor_id="reviewer-001")
        case = case.transition(WorkflowEvent.PREPARE_SYNC, actor_id="workflow-agent")

        self.assertEqual(WorkflowState.READY_TO_SYNC, case.state)
        self.assertEqual(5, case.version)
        self.assertEqual(4, len(case.audit_events))

    def test_cannot_skip_human_review(self) -> None:
        case = WorkflowCase(case_id="CASE-SYNTHETIC-002")
        case = case.transition(WorkflowEvent.OCR_SUCCEEDED, actor_id="ocr-worker")

        with self.assertRaisesRegex(ValueError, "Invalid transition"):
            case.transition(WorkflowEvent.PREPARE_SYNC, actor_id="workflow-agent")

    def test_rejection_requires_reason(self) -> None:
        case = WorkflowCase(case_id="CASE-SYNTHETIC-003")
        case = case.transition(WorkflowEvent.OCR_SUCCEEDED, actor_id="ocr-worker")
        case = case.transition(WorkflowEvent.REQUEST_REVIEW, actor_id="policy-engine")

        with self.assertRaisesRegex(ValueError, "reason"):
            case.transition(WorkflowEvent.REJECT, actor_id="reviewer-001")

