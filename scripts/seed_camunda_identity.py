"""Create the local Camunda workflow groups and memberships idempotently.

This bootstrap is local-only. It never creates or stores a password; credentials
are read from CAMUNDA_USERNAME and CAMUNDA_PASSWORD (demo/demo by default for
the stock Camunda local image).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "config" / "camunda_local_identity.json"


class IdentityClient(Protocol):
    def user_exists(self, user_id: str) -> bool: ...

    def group_exists(self, group_id: str) -> bool: ...

    def create_group(self, group: dict[str, str]) -> None: ...

    def membership_exists(self, group_id: str, user_id: str) -> bool: ...

    def add_member(self, group_id: str, user_id: str) -> None: ...


@dataclass(frozen=True)
class SeedResult:
    groups_created: tuple[str, ...]
    groups_existing: tuple[str, ...]
    memberships_added: tuple[tuple[str, str], ...]
    memberships_existing: tuple[tuple[str, str], ...]


class CamundaIdentityClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        self._authorization = f"Basic {token}"

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        allow_status: frozenset[int] = frozenset(),
    ) -> tuple[int, Any]:
        body = (
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
            if payload is not None
            else None
        )
        headers = {
            "Accept": "application/json",
            "Authorization": self._authorization,
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=15) as response:
                content = response.read()
                status = response.status
        except HTTPError as error:
            if error.code not in allow_status:
                raise RuntimeError(
                    f"Camunda identity request failed: HTTP {error.code} {method} {path}"
                ) from error
            return error.code, None
        except URLError as error:
            raise RuntimeError("Camunda identity endpoint is unavailable") from error
        if not content:
            return status, None
        try:
            return status, json.loads(content.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Camunda identity returned invalid JSON: {method} {path}"
            ) from error

    def user_exists(self, user_id: str) -> bool:
        status, payload = self._request(
            "GET",
            f"/user?id={quote(user_id, safe='')}",
            allow_status=frozenset({404}),
        )
        return status == 200 and _collection_contains_id(payload, user_id)

    def group_exists(self, group_id: str) -> bool:
        status, payload = self._request(
            "GET",
            f"/group?id={quote(group_id, safe='')}",
            allow_status=frozenset({404}),
        )
        return status == 200 and _collection_contains_id(payload, group_id)

    def create_group(self, group: dict[str, str]) -> None:
        self._request("POST", "/group/create", group)

    def add_member(self, group_id: str, user_id: str) -> None:
        self._request("PUT", f"/group/{group_id}/members/{user_id}")

    def membership_exists(self, group_id: str, user_id: str) -> bool:
        status, payload = self._request(
            "GET",
            f"/group?member={quote(user_id, safe='')}",
            allow_status=frozenset({404}),
        )
        return status == 200 and _collection_contains_id(payload, group_id)


def _collection_contains_id(payload: Any, expected_id: str) -> bool:
    if isinstance(payload, dict):
        return payload.get("id") == expected_id
    if isinstance(payload, list):
        return any(isinstance(item, dict) and item.get("id") == expected_id for item in payload)
    return False


def load_manifest(path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != "1.0.0" or payload.get("environment") != "local":
        raise ValueError("Camunda identity manifest must be local schemaVersion 1.0.0")
    groups = payload.get("groups")
    memberships = payload.get("memberships")
    if not isinstance(groups, list) or not isinstance(memberships, list):
        raise ValueError("Camunda identity manifest must contain groups and memberships arrays")
    group_ids: set[str] = set()
    for group in groups:
        if not isinstance(group, dict) or not all(
            isinstance(group.get(key), str) and group[key].strip()
            for key in ("id", "name", "type")
        ):
            raise ValueError("Camunda identity groups require non-empty id, name and type")
        group_ids.add(group["id"])
    if len(group_ids) != len(groups):
        raise ValueError("Camunda identity group IDs must be unique")
    for membership in memberships:
        if not isinstance(membership, dict):
            raise ValueError("Camunda identity membership must be an object")
        if membership.get("groupId") not in group_ids:
            raise ValueError("Camunda identity membership references an unknown group")
        if not isinstance(membership.get("userId"), str) or not membership["userId"].strip():
            raise ValueError("Camunda identity membership requires a userId")
    return groups, memberships


def seed_identity(client: IdentityClient, manifest_path: Path) -> SeedResult:
    groups, memberships = load_manifest(manifest_path)
    user_ids = {membership["userId"] for membership in memberships}
    missing_users = sorted(user_id for user_id in user_ids if not client.user_exists(user_id))
    if missing_users:
        raise RuntimeError(f"Camunda local users are missing: {', '.join(missing_users)}")

    created: list[str] = []
    existing: list[str] = []
    for group in groups:
        group_id = group["id"]
        if client.group_exists(group_id):
            existing.append(group_id)
        else:
            client.create_group(group)
            created.append(group_id)

    added: list[tuple[str, str]] = []
    existing_memberships: list[tuple[str, str]] = []
    for membership in memberships:
        group_id = membership["groupId"]
        user_id = membership["userId"]
        membership_key = (group_id, user_id)
        if client.membership_exists(group_id, user_id):
            existing_memberships.append(membership_key)
        else:
            client.add_member(group_id, user_id)
            added.append(membership_key)
    return SeedResult(tuple(created), tuple(existing), tuple(added), tuple(existing_memberships))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine-rest-url",
        default=os.getenv("CAMUNDA_REST_URL", "http://127.0.0.1:8080/engine-rest"),
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--username", default=os.getenv("CAMUNDA_USERNAME", "demo"))
    parser.add_argument(
        "--password",
        default=os.getenv("CAMUNDA_PASSWORD", "demo"),
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    result = seed_identity(
        CamundaIdentityClient(args.engine_rest_url, args.username, args.password),
        args.manifest.resolve(),
    )
    print(
        json.dumps(
            {
                "status": "SEEDED",
                "groupsCreated": list(result.groups_created),
                "groupsAlreadyPresent": list(result.groups_existing),
                "membershipsAdded": len(result.memberships_added),
                "membershipsAlreadyPresent": len(result.memberships_existing),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
