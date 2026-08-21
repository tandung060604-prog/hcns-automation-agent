from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "ocr_lab" / "api"
sys.path.insert(0, str(API_ROOT))

from mvp_demo_store import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_HR,
    ROLE_USER,
    MvpDemoError,
    MvpDemoStore,
)


def test_seed_assignment_tree_and_archive_copies(tmp_path: Path) -> None:
    store = MvpDemoStore(tmp_path)
    admin = {"username": "admin", "role": ROLE_ADMIN, "displayName": "Admin"}
    tree = store.org_tree(admin)
    assert any(node["username"] == "hr" for node in tree["hrNodes"])
    hr_node = next(node for node in tree["hrNodes"] if node["username"] == "hr")
    assert any(user["username"] == "user" for user in hr_node["users"])

    source = tmp_path / "don.docx"
    source.write_bytes(b"PK-fake-docx")
    application_id = "LOCAL-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    document_id = "00000000-0000-4000-8000-000000000321"

    opened = store.open_archive(
        application_id=application_id,
        document_id=document_id,
        owner="user",
        document_type="LEAVE_REQUEST",
        extracted_fields={"employeeName": "Nguyễn Văn An", "leaveDays": 2},
        source_file="don.docx",
        source_path=source,
        submitted_by_display="Nguyễn Văn An",
    )
    assert opened["submittedDate"]
    assert opened["submittedTime"]
    assert opened["managedByHr"] == "hr"
    assert opened["downloadReady"] is False
    assert opened["sourceFormat"] == "docx"
    assert store.archive_source_path(application_id) is not None

    try:
        store.open_archive(
            application_id="LOCAL-cccccccc-bbbb-4ccc-8ddd-ffffffffffff",
            document_id="00000000-0000-4000-8000-000000000399",
            owner="user",
            document_type="LEAVE_REQUEST",
            extracted_fields={"employeeName": "X"},
            source_file="missing.docx",
            source_path=None,
        )
        raise AssertionError("must require original file")
    except MvpDemoError as exc:
        assert "file gốc" in str(exc).lower() or "DOCX" in str(exc)

    user = {"username": "user", "role": ROLE_USER, "displayName": "Nguyễn Văn An"}
    hr = {"username": "hr", "role": ROLE_HR, "displayName": "HR"}
    user_copy = store.list_archive_for(user)
    hr_copy = store.list_archive_for(hr)
    assert len(user_copy) == 1
    assert len(hr_copy) == 1
    assert user_copy[0]["applicationId"] == application_id

    finalized = store.finalize_archive(
        application_id=application_id,
        decision="CONFIRMED",
        reviewed_by="hr",
        source_path=source,
    )
    assert finalized is not None
    assert finalized["decision"] == "CONFIRMED"
    assert finalized["downloadReady"] is True
    assert store.archive_source_path(application_id) is not None

    rejected_id = "LOCAL-bbbbbbbb-bbbb-4ccc-8ddd-ffffffffffff"
    pdf = tmp_path / "don2.pdf"
    pdf.write_bytes(b"%PDF-fake")
    store.open_archive(
        application_id=rejected_id,
        document_id="00000000-0000-4000-8000-000000000322",
        owner="user",
        document_type="LEAVE_REQUEST",
        extracted_fields={"employeeName": "Nguyễn Văn An"},
        source_file="don2.pdf",
        source_path=pdf,
    )
    rejected = store.finalize_archive(
        application_id=rejected_id,
        decision="REJECTED",
        reviewed_by="hr",
        source_path=pdf,
    )
    assert rejected is not None
    assert rejected["downloadReady"] is False
    assert rejected["sourceFormat"] == "pdf"

    try:
        store.list_archive_for(admin)
        raise AssertionError("admin must not keep archive copies")
    except MvpDemoError as exc:
        assert exc.status == 403


def test_assign_user_to_hr_updates_tree(tmp_path: Path) -> None:
    store = MvpDemoStore(tmp_path)
    admin = {"username": "admin", "role": ROLE_ADMIN, "displayName": "Admin"}
    created = store.create_user(
        admin,
        "user2",
        "user2123",
        ROLE_USER,
        "User Hai",
        managed_by="hr",
    )
    assert created["username"] == "user2"
    assert "user2" in store.managed_usernames("hr")
    assert store.hr_of_user("user2") == "hr"
