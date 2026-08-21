from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "ocr_lab" / "api"
sys.path.insert(0, str(API_ROOT))

from mvp_demo_store import (  # noqa: E402
    EVENT_NOTIFICATION,
    MvpDemoStore,
)


def test_hr_reject_notification_reaches_user(tmp_path: Path) -> None:
    store = MvpDemoStore(tmp_path)
    application_id = "LOCAL-11111111-2222-3333-444444444444"
    document_id = "00000000-0000-4000-8000-000000000099"

    store.bind_document(
        {"username": "user", "role": "USER", "displayName": "User"},
        document_id,
        application_id,
    )
    notification = store.notify(
        "user",
        "HR đã từ chối đơn của bạn",
        kind="REJECTED",
        application_id=application_id,
        document_id=document_id,
    )

    assert notification["kind"] == "REJECTED"
    assert notification["message"] == "HR đã từ chối đơn của bạn"

    user = store.user_by_token(store.login("user", "user123")["token"])
    assert user is not None
    events, _ = store.events_since(user, 0)
    assert events[-1]["kind"] == EVENT_NOTIFICATION
    assert events[-1]["payload"]["notification"]["message"] == "HR đã từ chối đơn của bạn"

    saved = store.notifications_for("user")
    assert saved[0]["kind"] == "REJECTED"
    assert "từ chối" in saved[0]["message"]
