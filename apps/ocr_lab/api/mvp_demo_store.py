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

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
APPLICATION_ID_RE = re.compile(r"^LOCAL-[0-9a-fA-F-]{1,64}$")
DOCUMENT_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
TIMELINE_EVENT_RE = re.compile(r"^[A-Za-z0-9 _.:-]{1,120}$")
NOTIFICATION_MESSAGE_RE = re.compile(r"^[A-Za-z0-9 _À-ỹ.:-]{1,200}$")


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
        self._lock = threading.RLock()
        self._users_path = self.root / "users.json"
        self._sessions_path = self.root / "sessions.json"
        self._audit_path = self.root / "audit.json"
        self._notifications_path = self.root / "notifications.json"
        self._timeline_path = self.root / "timeline.json"
        self._ownership_path = self.root / "ownership.json"
        self._users = self._load(self._users_path, {})
        self._seed_users()

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
        self._audit(
            "admin-create-user",
            actor["username"],
            f"tạo tài khoản {username} role {role}",
        )
        return {"username": username, "role": role, "displayName": display_name or username}

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
            self._save(self._audit_path, entries[-200:])

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

    def owner_of(self, document_id: str) -> str | None:
        with self._lock:
            ownership = self._load(self._ownership_path, {})
            record = ownership.get(document_id)
            return record.get("owner") if record else None

    def owner_of_all(self) -> dict[str, str]:
        with self._lock:
            ownership = self._load(self._ownership_path, {})
            return {
                str(key): str(record.get("owner", ""))
                for key, record in ownership.items()
                if isinstance(record, dict)
            }

    def can_access(self, user: dict[str, Any], document_id: str) -> bool:
        owner = self.owner_of(document_id)
        if owner is None:
            return user["role"] in {ROLE_ADMIN, ROLE_HR}
        if user["role"] == ROLE_ADMIN:
            return True
        if user["role"] == ROLE_HR:
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
            events.append(
                {
                    "at": _utc_now(),
                    "event": event,
                    "detail": detail[:300],
                    "actor": actor,
                }
            )
            self._save(self._timeline_path, timeline)

    def timeline(self, application_id: str) -> list[dict[str, Any]]:
        with self._lock:
            timeline = self._load(self._timeline_path, {})
            return timeline.get(application_id, [])

    # ---------- notifications ----------
    def notify(self, owner: str, message: str) -> dict[str, Any]:
        if NOTIFICATION_MESSAGE_RE.fullmatch(message) is None:
            raise MvpDemoError("Nội dung notification không hợp lệ")
        with self._lock:
            notifications = self._load(self._notifications_path, {})
            items = notifications.setdefault(owner, [])
            notification = {
                "id": uuid.uuid4().hex,
                "message": message,
                "read": False,
                "createdAt": _utc_now(),
            }
            items.append(notification)
            self._save(self._notifications_path, notifications)
        return notification

    def notifications_for(self, username: str) -> list[dict[str, Any]]:
        with self._lock:
            notifications = self._load(self._notifications_path, {})
            items = notifications.get(username, [])
            return sorted(
                items, key=lambda item: item.get("createdAt", ""), reverse=True
            )

    def mark_notification_read(self, username: str, notification_id: str) -> None:
        with self._lock:
            notifications = self._load(self._notifications_path, {})
            items = notifications.get(username, [])
            for item in items:
                if item.get("id") == notification_id:
                    item["read"] = True
            self._save(self._notifications_path, notifications)


def build_public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": user["username"],
        "role": user["role"],
        "roleLabel": ROLE_LABELS.get(user["role"], user["role"]),
        "displayName": user["displayName"],
    }
