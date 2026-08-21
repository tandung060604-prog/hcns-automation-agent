"""Synthetic MVP demo store for the Plan §1.1 acceptance flow.

Handles local identity (synthetic accounts), sessions, RBAC roles,
document ownership, in-app notifications, audit and per-case timeline.
Nothing here touches real HRIS or notification side effects; data lives
under ``<data-root>/mvp_demo`` and is intentionally synthetic.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROLE_ADMIN = "ADMIN"
ROLE_HR = "HR_REVIEWER"
ROLE_USER = "USER"

ROLE_LABELS = {
    ROLE_ADMIN: "Quản trị viên",
    ROLE_HR: "HR Reviewer",
    ROLE_USER: "Nhân viên",
}

SEED_USERS: dict[str, tuple[str, str, str]] = {
    # username: (password, role, display name)
    "admin": ("admin123", ROLE_ADMIN, "Quản trị hệ thống"),
    "hr": ("hr123", ROLE_HR, "HR Nguyễn Thu"),
    "user": ("user123", ROLE_USER, "Nguyễn Văn An"),
}

# Default demo tree: which HR manages which users.
SEED_ASSIGNMENTS: dict[str, list[str]] = {
    "hr": ["user"],
}

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
APPLICATION_ID_RE = re.compile(r"^LOCAL-[0-9a-fA-F-]{1,64}$")
DOCUMENT_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
TIMELINE_EVENT_RE = re.compile(r"^[A-Za-z0-9 _.:-]{1,120}$")
NOTIFICATION_MESSAGE_RE = re.compile(r"^[\w .,:;()\[\]/@#+*'\"?!-]{1,200}$")
DECISION_RE = re.compile(r"^(CONFIRMED|REQUEST_REUPLOAD|REJECTED|SUBMITTED)$")

EVENT_NOTIFICATION = "NOTIFICATION"
EVENT_QUEUE_CHANGED = "QUEUE_CHANGED"
EVENT_TIMELINE = "TIMELINE"

MAX_BUFFERED_EVENTS = 500
MAX_ARCHIVE_ENTRIES = 500
MAX_AUDIT_ENTRIES = 500


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_password(password: str) -> str:
    return hashlib.sha256(("hcns-mvp-demo::" + password).encode("utf-8")).hexdigest()


class MvpDemoError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


class MvpDemoStore:
    def __init__(self, data_root: Path) -> None:
        self.root = data_root / "mvp_demo"
        self.root.mkdir(parents=True, exist_ok=True)
        self._archive_files_root = self.root / "archive_files"
        self._archive_files_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._events_changed = threading.Condition(self._lock)
        self._events: list[dict[str, Any]] = []
        self._event_seq = 0
        self._users_path = self.root / "users.json"
        self._sessions_path = self.root / "sessions.json"
        self._audit_path = self.root / "audit.json"
        self._notifications_path = self.root / "notifications.json"
        self._timeline_path = self.root / "timeline.json"
        self._ownership_path = self.root / "ownership.json"
        self._pending_hr_path = self.root / "pending_hr.json"
        self._submissions_path = self.root / "submissions.json"
        self._assignments_path = self.root / "assignments.json"
        self._archive_path = self.root / "archive.json"
        self._users = self._load(self._users_path, {})
        self._seed_users()
        self._seed_assignments()


    # ---------- persistence ----------
    def _load(self, path: Path, default: Any) -> Any:
        if not path.is_file():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def _save(self, path: Path, payload: Any) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _seed_users(self) -> None:
        with self._lock:
            changed = False
            for username, (password, role, display) in SEED_USERS.items():
                if username not in self._users:
                    self._users[username] = {
                        "username": username,
                        "role": role,
                        "displayName": display,
                        "passwordHash": _hash_password(password),
                        "active": True,
                        "createdAt": _utc_now(),
                        "createdBy": "seed",
                    }
                    changed = True
            if changed:
                self._save(self._users_path, self._users)

    def _seed_assignments(self) -> None:
        with self._lock:
            assignments = self._load(self._assignments_path, {})
            if not isinstance(assignments, dict):
                assignments = {}
            changed = False
            for hr_username, users in SEED_ASSIGNMENTS.items():
                if hr_username not in self._users:
                    continue
                current = assignments.get(hr_username)
                if not isinstance(current, list):
                    current = []
                    assignments[hr_username] = current
                    changed = True
                for username in users:
                    if username in self._users and username not in current:
                        current.append(username)
                        changed = True
            if changed:
                self._save(self._assignments_path, assignments)

    # ---------- identity / auth ----------
    def login(self, username: str, password: str) -> dict[str, Any]:
        with self._lock:
            user = self._users.get(username)
            if user is None or not user.get("active", True):
                raise MvpDemoError("Tên đăng nhập hoặc mật khẩu sai", 401)
            if not secrets.compare_digest(
                user["passwordHash"], _hash_password(password)
            ):
                raise MvpDemoError("Tên đăng nhập hoặc mật khẩu sai", 401)
            token = uuid.uuid4().hex
            sessions = self._load(self._sessions_path, {})
            sessions[token] = {"username": username, "createdAt": _utc_now()}
            self._save(self._sessions_path, sessions)
            self._audit("login", username, "đăng nhập")
            return {
                "token": token,
                "username": username,
                "role": user["role"],
                "roleLabel": ROLE_LABELS.get(user["role"], user["role"]),
                "displayName": user["displayName"],
            }

    def logout(self, token: str) -> None:
        with self._lock:
            sessions = self._load(self._sessions_path, {})
            if token in sessions:
                del sessions[token]
                self._save(self._sessions_path, sessions)

    def user_by_token(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self._lock:
            sessions = self._load(self._sessions_path, {})
            session = sessions.get(token)
            if session is None:
                return None
            user = self._users.get(str(session.get("username")))
            if user is None or not user.get("active", True):
                return None
            return dict(user)

    def require_roles(self, token: str | None, roles: set[str]) -> dict[str, Any]:
        user = self.user_by_token(token)
        if user is None:
            raise MvpDemoError("Chưa đăng nhập", 401)
        if user["role"] not in roles:
            raise MvpDemoError("Role không có quyền thực hiện thao tác này", 403)
        return user

    # ---------- admin ----------
    def create_user(
        self,
        actor: dict[str, Any],
        username: str,
        password: str,
        role: str,
        display_name: str,
        *,
        managed_by: str | None = None,
    ) -> dict[str, Any]:
        if actor["role"] != ROLE_ADMIN:
            raise MvpDemoError("Chỉ ADMIN được tạo tài khoản", 403)
        if USERNAME_RE.fullmatch(username) is None:
            raise MvpDemoError("Username không hợp lệ (3-32 ký tự a-zA-Z0-9._-)")
        if role not in {ROLE_USER, ROLE_HR}:
            raise MvpDemoError("Role chỉ nhận USER hoặc HR_REVIEWER")
        if len(password) < 6:
            raise MvpDemoError("Mật khẩu tối thiểu 6 ký tự")
        with self._lock:
            if username in self._users:
                raise MvpDemoError("Username đã tồn tại", 409)
            self._users[username] = {
                "username": username,
                "role": role,
                "displayName": display_name or username,
                "passwordHash": _hash_password(password),
                "active": True,
                "createdAt": _utc_now(),
                "createdBy": actor["username"],
            }
            self._save(self._users_path, self._users)
        if role == ROLE_USER:
            hr_username = managed_by
            if not hr_username:
                hrs = self.usernames_with_roles({ROLE_HR})
                hr_username = hrs[0] if hrs else None
            if hr_username:
                self.assign_user_to_hr(actor, username, hr_username)
        self._audit(
            "admin-create-user",
            actor["username"],
            f"tạo tài khoản {username} role {role}"
            + (f" managedBy {managed_by}" if managed_by else ""),
        )
        return {
            "username": username,
            "role": role,
            "displayName": display_name or username,
            "managedBy": managed_by,
        }

    def set_user_active(
        self, actor: dict[str, Any], username: str, active: bool
    ) -> dict[str, Any]:
        if actor["role"] != ROLE_ADMIN:
            raise MvpDemoError("Chỉ ADMIN được đổi trạng thái tài khoản", 403)
        with self._lock:
            user = self._users.get(username)
            if user is None:
                raise MvpDemoError("Không tìm thấy tài khoản", 404)
            if username == actor["username"]:
                raise MvpDemoError("Không thể vô hiệu tài khoản của chính mình")
            user["active"] = active
            self._save(self._users_path, self._users)
        self._audit(
            "admin-toggle-user",
            actor["username"],
            f"{'khoá' if not active else 'mở'} tài khoản {username}",
        )
        return {"username": username, "active": active}

    def list_users(self, actor: dict[str, Any]) -> list[dict[str, Any]]:
        if actor["role"] != ROLE_ADMIN:
            raise MvpDemoError("Chỉ ADMIN được xem danh sách tài khoản", 403)
        return [
            {
                "username": u["username"],
                "role": u["role"],
                "roleLabel": ROLE_LABELS.get(u["role"], u["role"]),
                "displayName": u["displayName"],
                "active": u.get("active", True),
                "createdAt": u.get("createdAt", ""),
                "createdBy": u.get("createdBy", ""),
            }
            for u in self._users.values()
        ]

    def audit_log(self, actor: dict[str, Any]) -> list[dict[str, Any]]:
        if actor["role"] != ROLE_ADMIN:
            raise MvpDemoError("Chỉ ADMIN được xem audit log", 403)
        return self._load(self._audit_path, [])

    def _audit(self, action: str, actor: str, detail: str) -> None:
        with self._lock:
            entries = self._load(self._audit_path, [])
            entries.append(
                {
                    "at": _utc_now(),
                    "action": action,
                    "actor": actor,
                    "detail": detail,
                }
            )
            self._save(self._audit_path, entries[-MAX_AUDIT_ENTRIES:])

    # ---------- HR ↔ User assignment tree ----------
    def assign_user_to_hr(
        self, actor: dict[str, Any], username: str, hr_username: str
    ) -> dict[str, Any]:
        if actor["role"] != ROLE_ADMIN:
            raise MvpDemoError("Chỉ ADMIN được gán User cho HR", 403)
        with self._lock:
            user = self._users.get(username)
            hr = self._users.get(hr_username)
            if user is None or user.get("role") != ROLE_USER:
                raise MvpDemoError("User không hợp lệ", 404)
            if hr is None or hr.get("role") != ROLE_HR:
                raise MvpDemoError("HR không hợp lệ", 404)
            assignments = self._load(self._assignments_path, {})
            # Remove user from any previous HR bucket.
            for managed in assignments.values():
                if isinstance(managed, list) and username in managed:
                    managed.remove(username)
            bucket = assignments.setdefault(hr_username, [])
            if not isinstance(bucket, list):
                bucket = []
                assignments[hr_username] = bucket
            if username not in bucket:
                bucket.append(username)
            self._save(self._assignments_path, assignments)
        self._audit(
            "admin-assign-user",
            actor["username"],
            f"gán {username} cho HR {hr_username}",
        )
        return {"username": username, "managedBy": hr_username}

    def managed_usernames(self, hr_username: str) -> list[str]:
        with self._lock:
            assignments = self._load(self._assignments_path, {})
            managed = assignments.get(hr_username, [])
            if not isinstance(managed, list):
                return []
            return [str(item) for item in managed if isinstance(item, str)]

    def hr_of_user(self, username: str) -> str | None:
        with self._lock:
            assignments = self._load(self._assignments_path, {})
            for hr_username, managed in assignments.items():
                if isinstance(managed, list) and username in managed:
                    return str(hr_username)
            return None

    def org_tree(self, actor: dict[str, Any]) -> dict[str, Any]:
        """Admin-facing HR → User tree for tracking responsibility."""
        if actor["role"] != ROLE_ADMIN:
            raise MvpDemoError("Chỉ ADMIN được xem sơ đồ HR-User", 403)
        with self._lock:
            assignments = self._load(self._assignments_path, {})
            hrs = [
                user
                for user in self._users.values()
                if user.get("role") == ROLE_HR
            ]
            tree = []
            assigned_users: set[str] = set()
            for hr in sorted(hrs, key=lambda item: str(item.get("username", ""))):
                hr_username = str(hr["username"])
                managed = [
                    {
                        "username": username,
                        "displayName": self._users.get(username, {}).get(
                            "displayName", username
                        ),
                        "role": ROLE_USER,
                        "active": self._users.get(username, {}).get("active", True),
                    }
                    for username in self.managed_usernames(hr_username)
                    if username in self._users
                ]
                assigned_users.update(item["username"] for item in managed)
                tree.append(
                    {
                        "username": hr_username,
                        "displayName": hr.get("displayName", hr_username),
                        "role": ROLE_HR,
                        "active": hr.get("active", True),
                        "users": managed,
                    }
                )
            unassigned = [
                {
                    "username": user["username"],
                    "displayName": user.get("displayName", user["username"]),
                    "role": ROLE_USER,
                    "active": user.get("active", True),
                }
                for user in self._users.values()
                if user.get("role") == ROLE_USER
                and user["username"] not in assigned_users
            ]
            return {
                "admin": {
                    "username": actor["username"],
                    "displayName": actor.get("displayName", actor["username"]),
                },
                "hrNodes": tree,
                "unassignedUsers": unassigned,
            }

    # ---------- ownership / timeline ----------
    def bind_document(
        self, actor: dict[str, Any], document_id: str, application_id: str
    ) -> None:
        if DOCUMENT_ID_RE.fullmatch(document_id) is None:
            raise MvpDemoError("Document id không hợp lệ")
        with self._lock:
            ownership = self._load(self._ownership_path, {})
            ownership[document_id] = {
                "owner": actor["username"],
                "applicationId": application_id,
                "boundAt": _utc_now(),
            }
            self._save(self._ownership_path, ownership)

    def claim_document(self, actor: dict[str, Any], document_id: str) -> None:
        """Mark an uploaded document as owned before a case exists for it."""
        if DOCUMENT_ID_RE.fullmatch(document_id) is None:
            raise MvpDemoError("Document id không hợp lệ")
        with self._lock:
            ownership = self._load(self._ownership_path, {})
            if document_id in ownership:
                return
            ownership[document_id] = {
                "owner": actor["username"],
                "applicationId": "",
                "boundAt": _utc_now(),
            }
            self._save(self._ownership_path, ownership)

    def owner_of(self, document_id: str) -> str | None:
        with self._lock:
            ownership = self._load(self._ownership_path, {})
            record = ownership.get(document_id)
            return record.get("owner") if record else None

    def application_of(self, document_id: str) -> str:
        with self._lock:
            ownership = self._load(self._ownership_path, {})
            record = ownership.get(document_id)
            return str(record.get("applicationId", "")) if record else ""

    def owner_of_all(self) -> dict[str, str]:
        with self._lock:
            ownership = self._load(self._ownership_path, {})
            return {
                str(key): str(record.get("owner", ""))
                for key, record in ownership.items()
                if isinstance(record, dict)
            }

    def save_submission(
        self,
        *,
        application_id: str,
        document_id: str,
        owner: str,
        document_type: str,
        extracted_fields: dict[str, Any],
        source_file: str | None = None,
    ) -> dict[str, Any]:
        """Persist the extracted fields the user submitted for HR review."""
        if APPLICATION_ID_RE.fullmatch(application_id) is None:
            raise MvpDemoError("Application id không hợp lệ")
        if DOCUMENT_ID_RE.fullmatch(document_id) is None:
            raise MvpDemoError("Document id không hợp lệ")
        if not isinstance(extracted_fields, dict):
            raise MvpDemoError("Extracted fields không hợp lệ")
        cleaned: dict[str, Any] = {}
        for key, value in extracted_fields.items():
            if not isinstance(key, str) or not key or len(key) > 80:
                continue
            if isinstance(value, bool) or value is None:
                cleaned[key] = value
            elif isinstance(value, (str, int, float)):
                cleaned[key] = value if not isinstance(value, str) else value[:500]
        entry = {
            "applicationId": application_id,
            "documentId": document_id,
            "owner": owner,
            "documentType": document_type,
            "extractedFields": cleaned,
            "sourceFile": (source_file or "")[:200],
            "submittedAt": _utc_now(),
        }
        with self._lock:
            submissions = self._load(self._submissions_path, {})
            submissions[application_id] = entry
            self._save(self._submissions_path, submissions)
        return entry

    def get_submission(self, application_id: str) -> dict[str, Any] | None:
        if APPLICATION_ID_RE.fullmatch(application_id) is None:
            return None
        with self._lock:
            submissions = self._load(self._submissions_path, {})
            item = submissions.get(application_id)
            return dict(item) if isinstance(item, dict) else None

    def get_submission_by_document(self, document_id: str) -> dict[str, Any] | None:
        if DOCUMENT_ID_RE.fullmatch(document_id) is None:
            return None
        with self._lock:
            submissions = self._load(self._submissions_path, {})
            matches = [
                item
                for item in submissions.values()
                if isinstance(item, dict) and item.get("documentId") == document_id
            ]
            if not matches:
                return None
            return dict(
                sorted(
                    matches,
                    key=lambda item: str(item.get("submittedAt", "")),
                    reverse=True,
                )[0]
            )

    def open_archive(
        self,
        *,
        application_id: str,
        document_id: str,
        owner: str,
        document_type: str,
        extracted_fields: dict[str, Any],
        source_file: str | None = None,
        source_path: Path | None = None,
        submitted_by_display: str = "",
    ) -> dict[str, Any]:
        """Save local evidence metadata + keep the original uploaded file.

        Download stays locked until HR accepts (CONFIRMED). The original DOCX/PDF
        must be submitted with the case so History can later unlock it.
        """
        if APPLICATION_ID_RE.fullmatch(application_id) is None:
            raise MvpDemoError("Application id không hợp lệ")
        if DOCUMENT_ID_RE.fullmatch(document_id) is None:
            raise MvpDemoError("Document id không hợp lệ")
        if source_path is None or not source_path.is_file():
            raise MvpDemoError(
                "Phải gửi kèm file gốc (DOCX/PDF) khi nộp đơn",
                400,
            )
        suffix = source_path.suffix.casefold()
        if suffix not in {".docx", ".pdf", ".png", ".jpg", ".jpeg"}:
            raise MvpDemoError("File gốc phải là DOCX, PDF hoặc ảnh hỗ trợ")
        submitted_at = _utc_now()
        dest_dir = self._archive_files_root / application_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(source_file or source_path.name).name or source_path.name
        if not Path(safe_name).suffix:
            safe_name = f"{safe_name}{suffix}"
        dest = dest_dir / safe_name
        shutil.copy2(source_path, dest)
        archived_source = str(dest.relative_to(self.root))
        managed_by = self.hr_of_user(owner) or ""
        entry = {
            "applicationId": application_id,
            "documentId": document_id,
            "owner": owner,
            "ownerDisplayName": submitted_by_display or owner,
            "managedByHr": managed_by,
            "documentType": document_type,
            "extractedFields": dict(extracted_fields),
            "sourceFile": safe_name[:200],
            "sourceFormat": suffix.lstrip("."),
            "archivedSourcePath": archived_source,
            "downloadReady": False,
            "status": "SUBMITTED",
            "decision": "",
            "submittedAt": submitted_at,
            "submittedDate": submitted_at[:10],
            "submittedTime": submitted_at[11:19] if len(submitted_at) >= 19 else "",
            "decidedAt": "",
            "decidedDate": "",
            "decidedTime": "",
            "reviewedBy": "",
            "reviewedByDisplayName": "",
            "userCopyReady": True,
            "hrCopyReady": True,
        }
        with self._lock:
            archive = self._load(self._archive_path, {})
            archive[application_id] = entry
            if len(archive) > MAX_ARCHIVE_ENTRIES:
                ordered = sorted(
                    archive.items(),
                    key=lambda item: str(item[1].get("submittedAt", "")),
                )
                for key, _ in ordered[: len(archive) - MAX_ARCHIVE_ENTRIES]:
                    del archive[key]
            self._save(self._archive_path, archive)
        self._audit(
            "archive-open",
            owner,
            f"lưu bằng chứng nộp {application_id} kèm file gốc {safe_name}",
        )
        return dict(entry)

    def finalize_archive(
        self,
        *,
        application_id: str,
        decision: str,
        reviewed_by: str,
        note: str = "",
        source_path: Path | None = None,
    ) -> dict[str, Any] | None:
        """Stamp HR decision + reviewer account + accept datetime; unlock download on CONFIRMED."""
        if APPLICATION_ID_RE.fullmatch(application_id) is None:
            return None
        if DECISION_RE.fullmatch(decision) is None:
            raise MvpDemoError("Decision không hợp lệ")
        decided_at = _utc_now()
        with self._lock:
            archive = self._load(self._archive_path, {})
            entry = archive.get(application_id)
            if not isinstance(entry, dict):
                submission = self._load(self._submissions_path, {}).get(application_id)
                if not isinstance(submission, dict):
                    return None
                submitted_at = str(submission.get("submittedAt") or decided_at)
                entry = {
                    "applicationId": application_id,
                    "documentId": str(submission.get("documentId") or ""),
                    "owner": str(submission.get("owner") or ""),
                    "ownerDisplayName": str(submission.get("owner") or ""),
                    "managedByHr": self.hr_of_user(str(submission.get("owner") or "")) or "",
                    "documentType": str(submission.get("documentType") or ""),
                    "extractedFields": dict(submission.get("extractedFields") or {}),
                    "sourceFile": str(submission.get("sourceFile") or "")[:200],
                    "sourceFormat": Path(str(submission.get("sourceFile") or "")).suffix.casefold().lstrip("."),
                    "archivedSourcePath": "",
                    "downloadReady": False,
                    "status": "SUBMITTED",
                    "decision": "",
                    "submittedAt": submitted_at,
                    "submittedDate": submitted_at[:10],
                    "submittedTime": submitted_at[11:19] if len(submitted_at) >= 19 else "",
                    "decidedAt": "",
                    "decidedDate": "",
                    "decidedTime": "",
                    "reviewedBy": "",
                    "reviewedByDisplayName": "",
                    "userCopyReady": True,
                    "hrCopyReady": True,
                }
            # If accept and file was missing at submit time, try to attach now.
            if (
                decision == "CONFIRMED"
                and not entry.get("archivedSourcePath")
                and source_path is not None
                and source_path.is_file()
            ):
                dest_dir = self._archive_files_root / application_id
                dest_dir.mkdir(parents=True, exist_ok=True)
                safe_name = (
                    Path(str(entry.get("sourceFile") or source_path.name)).name
                    or source_path.name
                )
                dest = dest_dir / safe_name
                shutil.copy2(source_path, dest)
                entry["archivedSourcePath"] = str(dest.relative_to(self.root))
                entry["sourceFile"] = safe_name
                entry["sourceFormat"] = source_path.suffix.casefold().lstrip(".")
            reviewer = self._users.get(reviewed_by, {})
            entry["status"] = decision
            entry["decision"] = decision
            entry["reviewedBy"] = reviewed_by
            entry["reviewedByDisplayName"] = str(
                reviewer.get("displayName") or reviewed_by
            )
            entry["decisionNote"] = note[:200]
            entry["decidedAt"] = decided_at
            entry["decidedDate"] = decided_at[:10]
            entry["decidedTime"] = decided_at[11:19] if len(decided_at) >= 19 else ""
            if not entry.get("managedByHr"):
                entry["managedByHr"] = reviewed_by
            entry["downloadReady"] = bool(
                decision == "CONFIRMED" and entry.get("archivedSourcePath")
            )
            archive[application_id] = entry
            self._save(self._archive_path, archive)
            result = dict(entry)
        self._audit(
            "archive-finalize",
            reviewed_by,
            f"HR {reviewed_by} duyệt {application_id} → {decision} "
            f"ngày {result.get('decidedDate')} giờ {result.get('decidedTime')}"
            + (" · mở tải file gốc" if result.get("downloadReady") else ""),
        )
        return result

    def sync_archive_from_local_records(self) -> int:
        """Rebuild missing history rows from submissions + timeline (lazy migration)."""
        with self._lock:
            submissions = self._load(self._submissions_path, {})
            timeline = self._load(self._timeline_path, {})
            archive = self._load(self._archive_path, {})
            if not isinstance(submissions, dict):
                return 0
            if not isinstance(archive, dict):
                archive = {}
            changed = 0
            sessions_root = self.root.parent / "user_uploads" / "sessions"
            for application_id, submission in submissions.items():
                if not isinstance(submission, dict):
                    continue
                if APPLICATION_ID_RE.fullmatch(str(application_id) or "") is None:
                    continue
                entry = archive.get(application_id)
                if not isinstance(entry, dict):
                    submitted_at = str(submission.get("submittedAt") or _utc_now())
                    owner = str(submission.get("owner") or "")
                    source_file = str(submission.get("sourceFile") or "")
                    document_id = str(submission.get("documentId") or "")
                    archived_source = ""
                    # Best-effort attach original upload still on disk.
                    if document_id and sessions_root.is_dir():
                        input_dir = sessions_root / document_id / "input"
                        if input_dir.is_dir():
                            sources = sorted(input_dir.glob("document.*"))
                            if len(sources) == 1 and sources[0].is_file():
                                dest_dir = self._archive_files_root / application_id
                                dest_dir.mkdir(parents=True, exist_ok=True)
                                safe_name = Path(source_file or sources[0].name).name
                                dest = dest_dir / safe_name
                                shutil.copy2(sources[0], dest)
                                archived_source = str(dest.relative_to(self.root))
                                if not source_file:
                                    source_file = safe_name
                    entry = {
                        "applicationId": application_id,
                        "documentId": document_id,
                        "owner": owner,
                        "ownerDisplayName": self._users.get(owner, {}).get(
                            "displayName", owner
                        ),
                        "managedByHr": self.hr_of_user(owner) or "",
                        "documentType": str(submission.get("documentType") or ""),
                        "extractedFields": dict(submission.get("extractedFields") or {}),
                        "sourceFile": source_file[:200],
                        "sourceFormat": Path(source_file).suffix.casefold().lstrip("."),
                        "archivedSourcePath": archived_source,
                        "downloadReady": False,
                        "status": "SUBMITTED",
                        "decision": "",
                        "submittedAt": submitted_at,
                        "submittedDate": submitted_at[:10],
                        "submittedTime": submitted_at[11:19] if len(submitted_at) >= 19 else "",
                        "decidedAt": "",
                        "decidedDate": "",
                        "decidedTime": "",
                        "reviewedBy": "",
                        "reviewedByDisplayName": "",
                        "userCopyReady": True,
                        "hrCopyReady": True,
                    }
                    changed += 1
                # Apply latest HR review from timeline if archive lacks decision.
                if not entry.get("decision"):
                    events = timeline.get(application_id, []) if isinstance(timeline, dict) else []
                    if isinstance(events, list):
                        for event in reversed(events):
                            if not isinstance(event, dict):
                                continue
                            if event.get("event") != "HR_REVIEWED":
                                continue
                            detail = str(event.get("detail") or "")
                            decision = ""
                            if "CONFIRMED" in detail:
                                decision = "CONFIRMED"
                            elif "REJECTED" in detail:
                                decision = "REJECTED"
                            elif "REQUEST_REUPLOAD" in detail:
                                decision = "REQUEST_REUPLOAD"
                            if not decision:
                                continue
                            decided_at = str(event.get("at") or "")
                            reviewed_by = str(event.get("actor") or "")
                            entry["status"] = decision
                            entry["decision"] = decision
                            entry["reviewedBy"] = reviewed_by
                            entry["reviewedByDisplayName"] = str(
                                self._users.get(reviewed_by, {}).get(
                                    "displayName", reviewed_by
                                )
                            )
                            entry["decidedAt"] = decided_at
                            entry["decidedDate"] = decided_at[:10]
                            entry["decidedTime"] = (
                                decided_at[11:19] if len(decided_at) >= 19 else ""
                            )
                            if not entry.get("managedByHr"):
                                entry["managedByHr"] = reviewed_by
                            entry["downloadReady"] = bool(
                                decision == "CONFIRMED"
                                and entry.get("archivedSourcePath")
                            )
                            changed += 1
                            break
                archive[application_id] = entry
            if changed:
                self._save(self._archive_path, archive)
            return changed

    def get_archive(self, application_id: str) -> dict[str, Any] | None:
        if APPLICATION_ID_RE.fullmatch(application_id) is None:
            return None
        with self._lock:
            archive = self._load(self._archive_path, {})
            item = archive.get(application_id)
            return dict(item) if isinstance(item, dict) else None

    def archive_source_path(self, application_id: str) -> Path | None:
        entry = self.get_archive(application_id)
        if entry is None:
            return None
        relative = str(entry.get("archivedSourcePath") or "")
        if not relative:
            return None
        candidate = (self.root / relative).resolve()
        try:
            candidate.relative_to(self._archive_files_root.resolve())
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def list_archive_for(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        """User and HR keep evidence copies; Admin uses audit/org-tree instead."""
        self.sync_archive_from_local_records()
        role = user["role"]
        username = user["username"]
        with self._lock:
            archive = self._load(self._archive_path, {})
            items = [dict(item) for item in archive.values() if isinstance(item, dict)]
        if role == ROLE_ADMIN:
            raise MvpDemoError(
                "Admin theo dõi qua audit log và sơ đồ HR-User, không giữ bản bằng chứng đơn",
                403,
            )
        if role == ROLE_USER:
            visible = [item for item in items if item.get("owner") == username]
        elif role == ROLE_HR:
            managed = set(self.managed_usernames(username))
            visible = [
                item
                for item in items
                if item.get("reviewedBy") == username
                or item.get("managedByHr") == username
                or (managed and item.get("owner") in managed)
                or (not managed)
            ]
        else:
            visible = []
        return sorted(
            visible,
            key=lambda item: str(item.get("submittedAt", "")),
            reverse=True,
        )

    def can_access_archive(self, user: dict[str, Any], application_id: str) -> bool:
        entry = self.get_archive(application_id)
        if entry is None:
            return False
        if user["role"] == ROLE_ADMIN:
            return True
        if user["role"] == ROLE_USER:
            return entry.get("owner") == user["username"]
        if user["role"] == ROLE_HR:
            managed = self.managed_usernames(user["username"])
            if entry.get("reviewedBy") == user["username"]:
                return True
            if entry.get("managedByHr") == user["username"]:
                return True
            if managed:
                return entry.get("owner") in managed
            return True
        return False

    def register_hr_pending(
        self,
        *,
        application_id: str,
        document_id: str,
        owner: str,
        document_type: str,
        extracted_fields: dict[str, Any] | None = None,
    ) -> None:
        if APPLICATION_ID_RE.fullmatch(application_id) is None:
            raise MvpDemoError("Application id không hợp lệ")
        with self._lock:
            pending = self._load(self._pending_hr_path, {})
            pending[application_id] = {
                "applicationId": application_id,
                "documentId": document_id,
                "owner": owner,
                "documentType": document_type,
                "extractedFields": extracted_fields or {},
                "submittedAt": _utc_now(),
            }
            self._save(self._pending_hr_path, pending)

    def resolve_hr_pending(self, application_id: str) -> None:
        with self._lock:
            pending = self._load(self._pending_hr_path, {})
            if application_id in pending:
                del pending[application_id]
                self._save(self._pending_hr_path, pending)

    def list_hr_pending(self) -> list[dict[str, Any]]:
        with self._lock:
            pending = self._load(self._pending_hr_path, {})
            items = [
                item
                for item in pending.values()
                if isinstance(item, dict) and item.get("applicationId")
            ]
            return sorted(
                items,
                key=lambda item: str(item.get("submittedAt", "")),
                reverse=True,
            )

    def can_access(self, user: dict[str, Any], document_id: str) -> bool:
        owner = self.owner_of(document_id)
        if owner is None:
            return user["role"] in {ROLE_ADMIN, ROLE_HR}
        if user["role"] == ROLE_ADMIN:
            return True
        if user["role"] == ROLE_HR:
            managed = self.managed_usernames(user["username"])
            if managed:
                return owner in managed
            return True
        return user["username"] == owner

    def record_event(
        self,
        application_id: str,
        event: str,
        detail: str,
        actor: str,
    ) -> None:
        if APPLICATION_ID_RE.fullmatch(application_id) is None:
            raise MvpDemoError("Application id không hợp lệ")
        if TIMELINE_EVENT_RE.fullmatch(event) is None:
            raise MvpDemoError("Tên sự kiện không hợp lệ")
        with self._lock:
            timeline = self._load(self._timeline_path, {})
            events = timeline.setdefault(application_id, [])
            entry = {
                "at": _utc_now(),
                "event": event,
                "detail": detail[:300],
                "actor": actor,
            }
            events.append(entry)
            self._save(self._timeline_path, timeline)
        self.publish(
            EVENT_TIMELINE,
            target_roles=[ROLE_ADMIN, ROLE_HR],
            target_users=[actor] if actor != "system" else None,
            payload={"applicationId": application_id, "entry": entry},
        )

    def timeline(self, application_id: str) -> list[dict[str, Any]]:
        with self._lock:
            timeline = self._load(self._timeline_path, {})
            return timeline.get(application_id, [])

    # ---------- realtime event bus ----------
    def publish(
        self,
        kind: str,
        *,
        target_users: list[str] | None = None,
        target_roles: list[str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Broadcast one in-memory event to the SSE/polling subscribers.

        Events are transient by design: notifications and the timeline stay the
        durable source of truth, the bus only shortens the delivery latency.
        """
        with self._events_changed:
            self._event_seq += 1
            event = {
                "seq": self._event_seq,
                "at": _utc_now(),
                "kind": kind,
                "targetUsers": list(target_users or []),
                "targetRoles": list(target_roles or []),
                "payload": payload or {},
            }
            self._events.append(event)
            del self._events[:-MAX_BUFFERED_EVENTS]
            self._events_changed.notify_all()
            return event

    def _visible_to(self, event: dict[str, Any], user: dict[str, Any]) -> bool:
        users = event.get("targetUsers") or []
        roles = event.get("targetRoles") or []
        if not users and not roles:
            return True
        return user["username"] in users or user["role"] in roles

    def events_since(
        self, user: dict[str, Any], cursor: int
    ) -> tuple[list[dict[str, Any]], int]:
        with self._events_changed:
            events = [
                event
                for event in self._events
                if event["seq"] > cursor and self._visible_to(event, user)
            ]
            return events, self._event_seq

    def wait_for_events(
        self, user: dict[str, Any], cursor: int, timeout: float
    ) -> tuple[list[dict[str, Any]], int]:
        """Block until an event visible to ``user`` arrives or ``timeout`` ends."""
        with self._events_changed:
            events, latest = self.events_since(user, cursor)
            if events:
                return events, latest
            self._events_changed.wait(timeout)
            return self.events_since(user, cursor)

    # ---------- notifications ----------
    def notify(
        self,
        owner: str,
        message: str,
        *,
        kind: str = "INFO",
        application_id: str = "",
        document_id: str = "",
    ) -> dict[str, Any]:
        if NOTIFICATION_MESSAGE_RE.fullmatch(message) is None:
            raise MvpDemoError("Nội dung notification không hợp lệ")
        with self._lock:
            notifications = self._load(self._notifications_path, {})
            items = notifications.setdefault(owner, [])
            notification = {
                "id": uuid.uuid4().hex,
                "message": message,
                "kind": kind,
                "applicationId": application_id,
                "documentId": document_id,
                "read": False,
                "createdAt": _utc_now(),
            }
            items.append(notification)
            self._save(self._notifications_path, notifications)
        self.publish(
            EVENT_NOTIFICATION,
            target_users=[owner],
            payload={"notification": notification},
        )
        return notification

    def usernames_with_roles(self, roles: set[str]) -> list[str]:
        with self._lock:
            return sorted(
                username
                for username, user in self._users.items()
                if user.get("role") in roles and user.get("active", True)
            )

    def notify_roles(
        self,
        roles: set[str],
        message: str,
        *,
        kind: str = "INFO",
        application_id: str = "",
        document_id: str = "",
    ) -> list[dict[str, Any]]:
        """Fan one notification out to every active account holding ``roles``."""
        return [
            self.notify(
                username,
                message,
                kind=kind,
                application_id=application_id,
                document_id=document_id,
            )
            for username in self.usernames_with_roles(roles)
        ]

    def notifications_for(self, username: str) -> list[dict[str, Any]]:
        with self._lock:
            notifications = self._load(self._notifications_path, {})
            items = notifications.get(username, [])
            return sorted(
                items, key=lambda item: item.get("createdAt", ""), reverse=True
            )

    def mark_notification_read(self, username: str, notification_id: str) -> None:
        """Mark one notification read, or every notification when no id is given."""
        with self._lock:
            notifications = self._load(self._notifications_path, {})
            items = notifications.get(username, [])
            for item in items:
                if not notification_id or item.get("id") == notification_id:
                    item["read"] = True
            self._save(self._notifications_path, notifications)


def build_public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": user["username"],
        "role": user["role"],
        "roleLabel": ROLE_LABELS.get(user["role"], user["role"]),
        "displayName": user["displayName"],
    }
