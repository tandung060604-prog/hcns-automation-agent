from scripts.run_easyocr_external_dataset import (
    _candidate_allowed,
    _line_groups,
    _section_heading,
)


def _item(x: float, y: float, text: str) -> tuple[list[list[float]], str, float]:
    return ([[x, y], [x + 100, y], [x + 100, y + 20], [x, y + 20]], text, 0.9)


def test_line_groups_only_merge_same_baseline() -> None:
    groups = _line_groups([_item(20, 10, "left"), _item(140, 12, "right"), _item(20, 50, "next")])

    assert [[item[1] for item in group] for group in groups] == [["left", "right"], ["next"]]


def test_candidate_allowed_rejects_contact_and_short_noise() -> None:
    assert _candidate_allowed("Công ty TNHH Mây Việt", "Công ty")
    assert not _candidate_allowed("@example.com", "email")
    assert not _candidate_allowed("7", "một dòng")


def test_skill_section_heading_is_detected_for_refinement_guard() -> None:
    assert _section_heading("Kỹ năng") == "ky nang"
    assert _section_heading("Kinh nghiệm làm việc") == "kinh nghiem lam viec"
    assert _section_heading("một dòng kỹ năng") is None
