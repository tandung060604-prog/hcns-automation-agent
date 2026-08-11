from __future__ import annotations

from hcns_agent.templates.compatibility import canonicalize_template_payload


def test_legacy_cv_result_is_projected_to_canonical_v2_fields() -> None:
    payload = canonicalize_template_payload(
        {
            "templateId": "cv-v1",
            "templateVersion": "1.0",
            "data": {"fullName": "Synthetic", "phoneNumber": "000"},
            "quality": {"missingFields": ["phoneNumber"]},
            "detection": {"templateId": "cv-v1", "templateVersion": "1.0"},
            "camundaVariables": {"templateId": "cv-v1", "templateVersion": "1.0"},
        }
    )

    assert payload["templateId"] == "cv-v2"
    assert payload["templateVersion"] == "2.0"
    assert payload["schemaVersion"] == "2.0.0"
    assert payload["data"]["full_name"] == "Synthetic"
    assert payload["data"]["phone_number"] == "000"
    assert payload["data"]["desired_role"] is None
    assert payload["quality"]["missingFields"] == ["phone_number"]
    assert payload["camundaVariables"]["templateId"] == "cv-v2"


def test_canonical_result_is_idempotent() -> None:
    payload = {
        "templateId": "cv-v2",
        "templateVersion": "2.0",
        "data": {"full_name": "Synthetic"},
    }
    assert canonicalize_template_payload(payload) == payload
