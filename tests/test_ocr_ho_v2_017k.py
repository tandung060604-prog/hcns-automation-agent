from scripts.analyze_ocr_ho_v2_017k import classify_group, token_class, variant_family


def candidate(line_id: int, value: str, *, line_order: int = 0) -> dict[str, object]:
    return {
        "lineId": line_id,
        "lineIds": [line_id],
        "lineOrder": line_order,
        "value": value,
    }


def test_line_token_classes_are_separated() -> None:
    assert classify_group((1,), "A B", [candidate(2, "A B")]) == ("LINE_ID_MISS", False)
    assert classify_group(
        (1, 2),
        "A B",
        [candidate(2, "B", line_order=0), candidate(1, "A", line_order=1)],
    ) == ("LINE_ORDER_MISMATCH", False)
    assert classify_group((1,), "A B", [candidate(1, "A")]) == ("TOKEN_OMISSION", True)
    assert classify_group((1,), "A", [candidate(1, "A B")]) == ("TOKEN_EXTRA", True)
    assert classify_group((1,), "A B", [candidate(1, "B A")]) == ("TOKEN_SWAP", True)
    assert classify_group((1,), "A B", [candidate(1, "C D")]) == (
        "RECOGNIZER_DISAGREEMENT",
        True,
    )


def test_duplicate_line_and_variant_family_are_deterministic() -> None:
    assert classify_group(
        (1,),
        "A",
        [candidate(1, "A"), candidate(1, "A", line_order=1)],
    ) == ("DUPLICATE_LINE", False)
    assert token_class(("A",), ("A",)) == "EXACT_LINE_TOKEN"
    assert variant_family("line1_grayscale_clahe") == "grayscale_clahe"
    assert variant_family("color_original") == "color_original"
