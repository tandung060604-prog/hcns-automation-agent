from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "ocr_lab" / "api"
sys.path.insert(0, str(API_ROOT))

from mvp_demo_store import (  # noqa: E402
    EVENT_NOTIFICATION,
    ROLE_HR,
    MvpDemoStore,
)


def test_notify_roles_persists_and_publishes_realtime_event(tmp_path: Path) -> None:
    store = MvpDemoStore(tmp_path)

    notifications = store.notify_roles(
        {ROLE_HR},
        "Don moi cho duyet: Don xin nghi phep",
        kind="SUBMITTED",
        application_id="LOCAL-1234",
        document_id="00000000-0000-4000-8000-000000000000",
    )

    assert len(notifications) == 1
    assert notifications[0]["message"] == "Don moi cho duyet: Don xin nghi phep"
    assert store.notifications_for("hr")[0]["kind"] == "SUBMITTED"

    hr_user = store.user_by_token(store.login("hr", "hr123")["token"])
    assert hr_user is not None
    events, cursor = store.events_since(hr_user, 0)

    assert cursor >= 1
    assert events[-1]["kind"] == EVENT_NOTIFICATION
    assert events[-1]["payload"]["notification"]["kind"] == "SUBMITTED"


def test_hr_pending_queue_lifecycle(tmp_path: Path) -> None:
    store = MvpDemoStore(tmp_path)
    application_id = "LOCAL-aaaaaaaa-bbbb-cccc-dddddddddddd"

    store.register_hr_pending(
        application_id=application_id,
        document_id="00000000-0000-4000-8000-000000000001",
        owner="user",
        document_type="LEAVE_REQUEST",
        extracted_fields={"employeeName": "Nguyen Van A", "leaveDays": 2},
    )

    pending = store.list_hr_pending()
    assert len(pending) == 1
    assert pending[0]["applicationId"] == application_id
    assert pending[0]["extractedFields"]["employeeName"] == "Nguyen Van A"

    store.resolve_hr_pending(application_id)
    assert store.list_hr_pending() == []


def test_submission_snapshot_persists_extracted_fields(tmp_path: Path) -> None:
    store = MvpDemoStore(tmp_path)
    application_id = "LOCAL-11111111-2222-4333-8444-555555555555"
    document_id = "00000000-0000-4000-8000-000000000123"

    saved = store.save_submission(
        application_id=application_id,
        document_id=document_id,
        owner="user",
        document_type="LEAVE_REQUEST",
        extracted_fields={
            "employeeName": "Nguyễn Văn An",
            "department": "HCNS",
            "leaveDays": 3,
            "missingFields": ["should-drop"],
        },
        source_file="don_nghi.docx",
    )

    assert saved["extractedFields"]["employeeName"] == "Nguyễn Văn An"
    assert saved["extractedFields"]["leaveDays"] == 3
    assert "missingFields" not in saved["extractedFields"]

    by_app = store.get_submission(application_id)
    assert by_app is not None
    assert by_app["sourceFile"] == "don_nghi.docx"
    assert by_app["extractedFields"]["department"] == "HCNS"

    by_doc = store.get_submission_by_document(document_id)
    assert by_doc is not None
    assert by_doc["applicationId"] == application_id
