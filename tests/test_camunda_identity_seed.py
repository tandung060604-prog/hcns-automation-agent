from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from scripts.seed_camunda_identity import load_manifest, seed_identity


class FakeIdentityClient:
    def __init__(self) -> None:
        self.users = {"demo"}
        self.groups: set[str] = set()
        self.memberships: set[tuple[str, str]] = set()

    def user_exists(self, user_id: str) -> bool:
        return user_id in self.users

    def group_exists(self, group_id: str) -> bool:
        return group_id in self.groups

    def create_group(self, group: dict[str, str]) -> None:
        self.groups.add(group["id"])

    def membership_exists(self, group_id: str, user_id: str) -> bool:
        return (group_id, user_id) in self.memberships

    def add_member(self, group_id: str, user_id: str) -> None:
        self.memberships.add((group_id, user_id))


def test_local_manifest_matches_bpmn_candidate_groups() -> None:
    groups, memberships = load_manifest(Path("config/camunda_local_identity.json"))
    manifest_groups = {group["id"] for group in groups}
    assert manifest_groups == {"employees", "newHires", "hrReviewers"}
    bpmn = ElementTree.parse("camunda/HR_DOCUMENT_AGENT_MVP_V2.bpmn")
    camunda_namespace = "{http://camunda.org/schema/1.0/bpmn}candidateGroups"
    bpmn_groups = {
        group_id
        for task in bpmn.iter("{http://www.omg.org/spec/BPMN/20100524/MODEL}userTask")
        for group_id in task.attrib.get(camunda_namespace, "").split(",")
        if group_id
    }
    assert bpmn_groups == manifest_groups
    assert {(item["groupId"], item["userId"]) for item in memberships} == {
        ("employees", "demo"),
        ("newHires", "demo"),
        ("hrReviewers", "demo"),
    }


def test_seed_is_safe_to_run_again() -> None:
    client = FakeIdentityClient()
    first = seed_identity(client, Path("config/camunda_local_identity.json"))
    second = seed_identity(client, Path("config/camunda_local_identity.json"))

    assert first.groups_created == ("employees", "newHires", "hrReviewers")
    assert first.memberships_added == (
        ("employees", "demo"),
        ("newHires", "demo"),
        ("hrReviewers", "demo"),
    )
    assert second.groups_created == ()
    assert second.groups_existing == ("employees", "newHires", "hrReviewers")
    assert second.memberships_added == ()
    assert second.memberships_existing == (
        ("employees", "demo"),
        ("newHires", "demo"),
        ("hrReviewers", "demo"),
    )
    assert client.memberships == {
        ("employees", "demo"),
        ("newHires", "demo"),
        ("hrReviewers", "demo"),
    }
