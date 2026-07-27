"""Explicit, auditable workflow state transitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum


class WorkflowState(str, Enum):
    RECEIVED = "RECEIVED"
    OCR_COMPLETE = "OCR_COMPLETE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    READY_TO_SYNC = "READY_TO_SYNC"
    COMPLETED = "COMPLETED"


class WorkflowEvent(str, Enum):
    OCR_SUCCEEDED = "OCR_SUCCEEDED"
    REQUEST_REVIEW = "REQUEST_REVIEW"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    PREPARE_SYNC = "PREPARE_SYNC"
    SYNC_SUCCEEDED = "SYNC_SUCCEEDED"


_TRANSITIONS: dict[tuple[WorkflowState, WorkflowEvent], WorkflowState] = {
    (WorkflowState.RECEIVED, WorkflowEvent.OCR_SUCCEEDED): WorkflowState.OCR_COMPLETE,
    (WorkflowState.OCR_COMPLETE, WorkflowEvent.REQUEST_REVIEW): WorkflowState.REVIEW_REQUIRED,
    (WorkflowState.REVIEW_REQUIRED, WorkflowEvent.APPROVE): WorkflowState.APPROVED,
    (WorkflowState.REVIEW_REQUIRED, WorkflowEvent.REJECT): WorkflowState.REJECTED,
    (WorkflowState.APPROVED, WorkflowEvent.PREPARE_SYNC): WorkflowState.READY_TO_SYNC,
    (WorkflowState.READY_TO_SYNC, WorkflowEvent.SYNC_SUCCEEDED): WorkflowState.COMPLETED,
}


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event: WorkflowEvent
    from_state: WorkflowState
    to_state: WorkflowState
    actor_id: str
    occurred_at: datetime
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowCase:
    case_id: str
    state: WorkflowState = WorkflowState.RECEIVED
    version: int = 1
    audit_events: tuple[AuditEvent, ...] = ()

    def transition(
        self,
        event: WorkflowEvent,
        *,
        actor_id: str,
        reason: str | None = None,
    ) -> WorkflowCase:
        target = _TRANSITIONS.get((self.state, event))
        if target is None:
            raise ValueError(f"Invalid transition: {self.state} + {event}")
        if event is WorkflowEvent.REJECT and not reason:
            raise ValueError("A rejection reason is required")

        audit = AuditEvent(
            event=event,
            from_state=self.state,
            to_state=target,
            actor_id=actor_id,
            occurred_at=datetime.now(timezone.utc),
            reason=reason,
        )
        return replace(
            self,
            state=target,
            version=self.version + 1,
            audit_events=(*self.audit_events, audit),
        )
