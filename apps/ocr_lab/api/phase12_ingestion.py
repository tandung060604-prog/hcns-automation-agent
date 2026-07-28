#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical local ingestion for Phase 12 PDF, DOCX, XLSX, and images."""

from __future__ import annotations

import difflib
import math
import re
import textwrap
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_WORD = {"w": WORD_NS}
NS_SHEET = {"x": SHEET_NS, "r": REL_NS}
SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".pdf", ".docx", ".xlsx"}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").split())


def _key(value: Any) -> str:
    text = _clean(value).casefold().replace("đ", "d")
    import unicodedata

    decomposed = unicodedata.normalize("NFD", text)
    plain = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def _block(
    text: str,
    page_index: int,
    block_index: int,
    source_kind: str,
    confidence: float,
    *,
    bbox: Any = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    return {
        "blockIndex": block_index,
        "text": _clean(text),
        "sourceKind": source_kind,
        "confidence": round(float(confidence), 6),
        "evidence": {
            "pageIndex": page_index,
            "bbox": bbox,
            "sourceRef": source_ref,
        },
    }


def _ocr_blocks(
    page: dict[str, Any],
    page_index: int,
) -> list[dict[str, Any]]:
    texts = page.get("recognizedTexts", [])
    scores = page.get("recognitionScores", [])
    boxes = page.get("recognizedBoxes", [])
    output: list[dict[str, Any]] = []
    for index, text in enumerate(texts):
        cleaned = _clean(text)
        if not cleaned:
            continue
        output.append(
            _block(
                cleaned,
                page_index,
                len(output),
                "ocr",
                float(scores[index]) if index < len(scores) else 0.0,
                bbox=boxes[index] if index < len(boxes) else None,
                source_ref=f"page:{page_index}:ocr-line:{index}",
            )
        )
    return output


def _text_similarity(left: str, right: str) -> float:
    left_key = _key(left)
    right_key = _key(right)
    if not left_key or not right_key:
        return 0.0
    return difflib.SequenceMatcher(None, left_key, right_key).ratio()


def _merge_hybrid_blocks(
    native_blocks: list[dict[str, Any]],
    ocr_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output = [dict(block) for block in native_blocks]
    native_texts = [block["text"] for block in native_blocks]
    for block in ocr_blocks:
        if any(
            _text_similarity(block["text"], native_text) >= 0.86
            for native_text in native_texts
        ):
            continue
        copied = dict(block)
        copied["blockIndex"] = len(output)
        output.append(copied)
    return output


def _page_mode(
    native_blocks: list[dict[str, Any]],
    ocr_blocks: list[dict[str, Any]],
) -> tuple[str, float]:
    native_text = "\n".join(block["text"] for block in native_blocks)
    ocr_text = "\n".join(block["text"] for block in ocr_blocks)
    native_chars = len(_key(native_text).replace(" ", ""))
    ocr_chars = len(_key(ocr_text).replace(" ", ""))
    similarity = _text_similarity(native_text, ocr_text)
    if native_chars < 20:
        return ("scan" if ocr_chars else "empty"), similarity
    if ocr_chars < 20 or similarity >= 0.72:
        return "native", similarity
    return "hybrid", similarity


def _document_mode(pages: list[dict[str, Any]]) -> str:
    modes = {page["ingestionMode"] for page in pages}
    if not modes or modes == {"empty"}:
        return "EMPTY"
    if modes <= {"native", "empty"}:
        return "NATIVE"
    if modes <= {"scan", "empty"}:
        return "SCAN"
    return "HYBRID"


def _detect_delimited_tables(
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for page in pages:
        rows: list[dict[str, Any]] = []
        for block in page.get("blocks", []):
            text = block["text"]
            delimiter = "|" if text.count("|") >= 2 else "\t"
            if delimiter == "\t" and text.count("\t") < 2:
                continue
            values = [_clean(value) for value in text.split(delimiter)]
            if sum(bool(value) for value in values) < 3:
                continue
            rows.append(
                {
                    "rowIndex": len(rows),
                    "values": values,
                    "cells": [
                        {
                            "columnIndex": column_index,
                            "value": value,
                            "status": (
                                "accepted"
                                if block["sourceKind"] != "ocr"
                                else "needs_review"
                            ),
                            "evidence": block["evidence"],
                        }
                        for column_index, value in enumerate(values)
                    ],
                }
            )
        if len(rows) < 2:
            continue
        width = max(len(row["values"]) for row in rows)
        tables.append(
            {
                "tableIndex": len(tables),
                "pageIndex": page["pageIndex"],
                "sourceKind": "delimited_text",
                "columns": [
                    {
                        "columnIndex": index,
                        "name": (
                            rows[0]["values"][index]
                            if index < len(rows[0]["values"])
                            else f"column_{index + 1}"
                        ),
                    }
                    for index in range(width)
                ],
                "rows": rows[1:],
            }
        )
    return tables


def ingest_pdf(
    path: Path,
    ocr_pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    document = pdfium.PdfDocument(path)
    pages: list[dict[str, Any]] = []
    native_char_count = 0
    ocr_char_count = 0
    try:
        for page_index in range(len(document)):
            page = document[page_index]
            text_page = page.get_textpage()
            try:
                native_text = text_page.get_text_range() or ""
            finally:
                text_page.close()
                page.close()
            native_blocks = [
                _block(
                    line,
                    page_index,
                    block_index,
                    "pdf_text_layer",
                    1.0,
                    source_ref=f"page:{page_index}:native-line:{line_index}",
                )
                for line_index, line in enumerate(native_text.splitlines())
                if _clean(line)
                for block_index in [line_index]
            ]
            ocr_page = (
                ocr_pages[page_index]
                if ocr_pages and page_index < len(ocr_pages)
                else {}
            )
            ocr_blocks = _ocr_blocks(ocr_page, page_index)
            mode, similarity = _page_mode(native_blocks, ocr_blocks)
            if mode == "native":
                selected = native_blocks
            elif mode == "scan":
                selected = ocr_blocks
            elif mode == "hybrid":
                selected = _merge_hybrid_blocks(native_blocks, ocr_blocks)
            else:
                selected = []
            native_chars = sum(len(block["text"]) for block in native_blocks)
            page_ocr_chars = sum(len(block["text"]) for block in ocr_blocks)
            native_char_count += native_chars
            ocr_char_count += page_ocr_chars
            pages.append(
                {
                    "pageIndex": page_index,
                    "ingestionMode": mode,
                    "nativeOcrSimilarity": round(similarity, 6),
                    "nativeCharacterCount": native_chars,
                    "ocrCharacterCount": page_ocr_chars,
                    "blocks": selected,
                    "nativeBlocks": native_blocks,
                    "ocrBlocks": ocr_blocks,
                }
            )
    finally:
        document.close()
    return {
        "schemaVersion": "1.0.0",
        "sourceFormat": "PDF",
        "adapter": "pypdfium2_text_plus_paddleocr",
        "ingestionMode": _document_mode(pages),
        "pageCount": len(pages),
        "pages": pages,
        "tables": _detect_delimited_tables(pages),
        "plainText": "\n".join(
            block["text"] for page in pages for block in page["blocks"]
        ),
        "metadata": {
            "nativeCharacterCount": native_char_count,
            "ocrCharacterCount": ocr_char_count,
        },
    }


def _word_text(element: ET.Element) -> str:
    parts: list[str] = []
    for node in element.iter():
        if node.tag == f"{{{WORD_NS}}}t" and node.text:
            parts.append(node.text)
        elif node.tag == f"{{{WORD_NS}}}tab":
            parts.append("\t")
        elif node.tag in {
            f"{{{WORD_NS}}}br",
            f"{{{WORD_NS}}}cr",
        }:
            parts.append("\n")
    return _clean("".join(parts))


def _docx_table(
    element: ET.Element,
    table_index: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(element.findall("./w:tr", NS_WORD)):
        values = [
            _word_text(cell)
            for cell in row.findall("./w:tc", NS_WORD)
        ]
        rows.append(
            {
                "rowIndex": row_index,
                "values": values,
                "cells": [
                    {
                        "columnIndex": column_index,
                        "value": value,
                        "status": "accepted",
                        "evidence": {
                            "sourceRef": (
                                f"table:{table_index}:"
                                f"row:{row_index}:cell:{column_index}"
                            )
                        },
                    }
                    for column_index, value in enumerate(values)
                ],
            }
        )
    width = max((len(row["values"]) for row in rows), default=0)
    return {
        "tableIndex": table_index,
        "pageIndex": 0,
        "sourceKind": "docx_table",
        "columns": [
            {
                "columnIndex": index,
                "name": (
                    rows[0]["values"][index]
                    if rows and index < len(rows[0]["values"])
                    else f"column_{index + 1}"
                ),
            }
            for index in range(width)
        ],
        "rows": rows[1:] if len(rows) > 1 else rows,
        "allRows": rows,
    }


def ingest_docx(path: Path) -> dict[str, Any]:
    pages = [
        {
            "pageIndex": 0,
            "ingestionMode": "native",
            "blocks": [],
            "nativeBlocks": [],
            "ocrBlocks": [],
        }
    ]
    tables: list[dict[str, Any]] = []
    embedded_image_count = 0
    with zipfile.ZipFile(path) as package:
        names = set(package.namelist())
        if "word/document.xml" not in names:
            raise ValueError("DOCX package has no word/document.xml")
        root = ET.fromstring(package.read("word/document.xml"))
        body = root.find("./w:body", NS_WORD)
        if body is None:
            raise ValueError("DOCX document body is missing")
        blocks: list[dict[str, Any]] = []
        for child in body:
            if child.tag == f"{{{WORD_NS}}}p":
                text = _word_text(child)
                if text:
                    blocks.append(
                        _block(
                            text,
                            0,
                            len(blocks),
                            "docx_paragraph",
                            1.0,
                            source_ref=f"paragraph:{len(blocks)}",
                        )
                    )
            elif child.tag == f"{{{WORD_NS}}}tbl":
                table = _docx_table(child, len(tables))
                tables.append(table)
                for row in table.get("allRows", []):
                    text = " | ".join(
                        value for value in row["values"] if value
                    )
                    if text:
                        blocks.append(
                            _block(
                                text,
                                0,
                                len(blocks),
                                "docx_table",
                                1.0,
                                source_ref=(
                                    f"table:{table['tableIndex']}:"
                                    f"row:{row['rowIndex']}"
                                ),
                            )
                        )
        pages[0]["blocks"] = blocks
        pages[0]["nativeBlocks"] = blocks
        embedded_image_count = sum(
            name.startswith("word/media/") for name in names
        )
    return {
        "schemaVersion": "1.0.0",
        "sourceFormat": "DOCX",
        "adapter": "ooxml_docx",
        "ingestionMode": "NATIVE",
        "pageCount": 1,
        "paginationMode": "logical",
        "pages": pages,
        "tables": tables,
        "plainText": "\n".join(
            block["text"] for block in pages[0]["blocks"]
        ),
        "metadata": {
            "embeddedImageCount": embedded_image_count,
            "requiresImageOcr": embedded_image_count > 0,
        },
    }


def _column_index(cell_reference: str) -> int:
    match = re.match(r"([A-Z]+)", cell_reference.upper())
    if not match:
        return 0
    value = 0
    for character in match.group(1):
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def _shared_strings(package: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in package.namelist():
        return []
    root = ET.fromstring(package.read("xl/sharedStrings.xml"))
    return [
        _clean("".join(node.text or "" for node in item.findall(".//x:t", NS_SHEET)))
        for item in root.findall("./x:si", NS_SHEET)
    ]


def _xlsx_value(
    cell: ET.Element,
    shared_strings: list[str],
) -> tuple[Any, str | None]:
    cell_type = cell.attrib.get("t", "")
    formula_node = cell.find("./x:f", NS_SHEET)
    formula = formula_node.text if formula_node is not None else None
    if cell_type == "inlineStr":
        value = "".join(
            node.text or "" for node in cell.findall(".//x:is/x:t", NS_SHEET)
        )
        return _clean(value), formula
    value_node = cell.find("./x:v", NS_SHEET)
    raw = value_node.text if value_node is not None else ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw)], formula
        except (ValueError, IndexError):
            return raw, formula
    if cell_type == "b":
        return raw == "1", formula
    if cell_type in {"str", "e", "d"}:
        return _clean(raw), formula
    if raw == "":
        return "", formula
    try:
        number = float(raw)
        return int(number) if number.is_integer() else number, formula
    except ValueError:
        return _clean(raw), formula


def _xlsx_sheet_paths(
    package: zipfile.ZipFile,
) -> list[tuple[str, str]]:
    workbook = ET.fromstring(package.read("xl/workbook.xml"))
    relations = ET.fromstring(
        package.read("xl/_rels/workbook.xml.rels")
    )
    targets = {
        relation.attrib["Id"]: relation.attrib["Target"]
        for relation in relations.findall(f"./{{{PACKAGE_REL_NS}}}Relationship")
    }
    output: list[tuple[str, str]] = []
    for sheet in workbook.findall("./x:sheets/x:sheet", NS_SHEET):
        relation_id = sheet.attrib.get(f"{{{REL_NS}}}id", "")
        target = targets.get(relation_id)
        if not target:
            continue
        target_path = PurePosixPath(target.lstrip("/"))
        if not str(target_path).startswith("xl/"):
            target_path = PurePosixPath("xl") / target_path
        output.append((sheet.attrib.get("name", "Sheet"), str(target_path)))
    return output


def _header_row_index(rows: list[dict[str, Any]]) -> int:
    header_terms = {
        "ma nv",
        "ma nhan vien",
        "ho va ten",
        "phong ban",
        "ngay cong",
        "nghi phep",
        "gio tang ca",
        "trang thai",
    }
    best_index = 0
    best_score = -1
    for index, row in enumerate(rows[:20]):
        keys = [_key(value) for value in row["values"]]
        score = sum(
            any(term == key or term in key for term in header_terms)
            for key in keys
        )
        score += min(2, sum(bool(key) for key in keys) / 10)
        if score > best_score:
            best_score = score
            best_index = index
    return best_index


def ingest_xlsx(path: Path) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as package:
        names = set(package.namelist())
        required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
        if not required <= names:
            raise ValueError("XLSX package is missing workbook metadata")
        shared_strings = _shared_strings(package)
        for page_index, (sheet_name, sheet_path) in enumerate(
            _xlsx_sheet_paths(package)
        ):
            if sheet_path not in names:
                continue
            root = ET.fromstring(package.read(sheet_path))
            sparse_rows: list[dict[str, Any]] = []
            max_column = 0
            for row_node in root.findall(".//x:sheetData/x:row", NS_SHEET):
                row_number = int(row_node.attrib.get("r", len(sparse_rows) + 1))
                cells: dict[int, dict[str, Any]] = {}
                for cell_node in row_node.findall("./x:c", NS_SHEET):
                    reference = cell_node.attrib.get("r", "A1")
                    column = _column_index(reference)
                    value, formula = _xlsx_value(cell_node, shared_strings)
                    cells[column] = {
                        "cellRef": f"{sheet_name}!{reference}",
                        "value": value,
                        "formula": formula,
                        "status": "accepted",
                        "evidence": {
                            "sheetName": sheet_name,
                            "cellRef": reference,
                        },
                    }
                    max_column = max(max_column, column)
                if cells:
                    values = [
                        cells.get(index, {}).get("value", "")
                        for index in range(max_column + 1)
                    ]
                    sparse_rows.append(
                        {
                            "rowIndex": row_number,
                            "values": values,
                            "cells": [
                                cells.get(
                                    index,
                                    {
                                        "cellRef": (
                                            f"{sheet_name}!R{row_number}C{index + 1}"
                                        ),
                                        "value": "",
                                        "formula": None,
                                        "status": "not_found",
                                        "evidence": {
                                            "sheetName": sheet_name,
                                            "rowIndex": row_number,
                                            "columnIndex": index,
                                        },
                                    },
                                )
                                for index in range(max_column + 1)
                            ],
                        }
                    )
            for row in sparse_rows:
                missing = max_column + 1 - len(row["values"])
                if missing > 0:
                    row["values"].extend([""] * missing)
            header_index = _header_row_index(sparse_rows) if sparse_rows else 0
            header = sparse_rows[header_index] if sparse_rows else {
                "values": []
            }
            data_rows = sparse_rows[header_index + 1 :]
            merged_ranges = [
                node.attrib.get("ref")
                for node in root.findall(".//x:mergeCells/x:mergeCell", NS_SHEET)
                if node.attrib.get("ref")
            ]
            table = {
                "tableIndex": len(tables),
                "pageIndex": page_index,
                "sheetName": sheet_name,
                "sourceKind": "xlsx_cells",
                "headerRowIndex": header.get("rowIndex"),
                "columns": [
                    {
                        "columnIndex": index,
                        "name": _clean(value) or f"column_{index + 1}",
                        "cellRef": (
                            header["cells"][index]["cellRef"]
                            if index < len(header.get("cells", []))
                            else None
                        ),
                    }
                    for index, value in enumerate(header.get("values", []))
                ],
                "rows": data_rows,
                "allRows": sparse_rows,
                "mergedRanges": merged_ranges,
            }
            tables.append(table)
            blocks = [
                _block(
                    " | ".join(
                        _clean(value) for value in row["values"] if _clean(value)
                    ),
                    page_index,
                    block_index,
                    "xlsx_row",
                    1.0,
                    source_ref=f"{sheet_name}!{row['rowIndex']}:{row['rowIndex']}",
                )
                for block_index, row in enumerate(sparse_rows)
                if any(_clean(value) for value in row["values"])
            ]
            pages.append(
                {
                    "pageIndex": page_index,
                    "sheetName": sheet_name,
                    "ingestionMode": "native",
                    "blocks": blocks,
                    "nativeBlocks": blocks,
                    "ocrBlocks": [],
                }
            )
    return {
        "schemaVersion": "1.0.0",
        "sourceFormat": "XLSX",
        "adapter": "ooxml_xlsx",
        "ingestionMode": "NATIVE",
        "pageCount": len(pages),
        "paginationMode": "worksheet",
        "pages": pages,
        "tables": tables,
        "plainText": "\n".join(
            block["text"] for page in pages for block in page["blocks"]
        ),
        "metadata": {
            "sheetCount": len(pages),
            "formulaCellCount": sum(
                cell.get("formula") is not None
                for table in tables
                for row in table.get("allRows", [])
                for cell in row.get("cells", [])
            ),
        },
    }


def ingest_image(
    path: Path,
    ocr_pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    for page_index, ocr_page in enumerate(ocr_pages or []):
        blocks = _ocr_blocks(ocr_page, page_index)
        pages.append(
            {
                "pageIndex": page_index,
                "ingestionMode": "scan",
                "blocks": blocks,
                "nativeBlocks": [],
                "ocrBlocks": blocks,
            }
        )
    return {
        "schemaVersion": "1.0.0",
        "sourceFormat": path.suffix.lstrip(".").upper(),
        "adapter": "paddleocr_image",
        "ingestionMode": "SCAN",
        "pageCount": len(pages),
        "pages": pages,
        "tables": _detect_delimited_tables(pages),
        "plainText": "\n".join(
            block["text"] for page in pages for block in page["blocks"]
        ),
        "metadata": {},
    }


def ingest_document(
    path: Path,
    ocr_pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported Phase 12 format: {suffix}")
    if suffix == ".pdf":
        return ingest_pdf(path, ocr_pages)
    if suffix == ".docx":
        return ingest_docx(path)
    if suffix == ".xlsx":
        return ingest_xlsx(path)
    return ingest_image(path, ocr_pages)


def _font(size: int) -> ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def render_native_previews(
    canonical: dict[str, Any],
    pages_dir: Path,
    visualization_dir: Path,
) -> tuple[list[Path], list[dict[str, Any]]]:
    pages_dir.mkdir(parents=True, exist_ok=True)
    visualization_dir.mkdir(parents=True, exist_ok=True)
    font = _font(24)
    title_font = _font(30)
    page_paths: list[Path] = []
    page_results: list[dict[str, Any]] = []
    canonical_pages = canonical.get("pages", [])
    for page_index, page in enumerate(canonical_pages):
        blocks = page.get("blocks", [])
        wrapped: list[tuple[dict[str, Any], list[str]]] = []
        for block in blocks:
            lines = textwrap.wrap(
                block["text"],
                width=92,
                replace_whitespace=False,
            ) or [block["text"]]
            wrapped.append((block, lines))
        height = max(
            1000,
            120 + sum(max(1, len(lines)) * 34 + 12 for _, lines in wrapped),
        )
        image = Image.new("RGB", (1400, min(height, 5000)), "white")
        draw = ImageDraw.Draw(image)
        label = page.get("sheetName") or f"Trang {page_index + 1}"
        draw.text((60, 35), str(label), fill="#143d35", font=title_font)
        y = 100
        texts: list[str] = []
        scores: list[float] = []
        boxes: list[list[list[int]]] = []
        for block, lines in wrapped:
            top = y
            for line in lines:
                draw.text((60, y), line, fill="#17211f", font=font)
                y += 34
            bottom = max(top + 32, y)
            texts.append(block["text"])
            scores.append(float(block.get("confidence", 1.0)))
            boxes.append(
                [[50, top - 3], [1350, top - 3], [1350, bottom], [50, bottom]]
            )
            y += 12
        page_path = pages_dir / f"page_{page_index:03d}.png"
        visualization_path = (
            visualization_dir / f"page_{page_index:03d}.png"
        )
        image.save(page_path, format="PNG", optimize=True)
        image.save(visualization_path, format="PNG", optimize=True)
        page_paths.append(page_path)
        page_results.append(
            {
                "pageIndex": page_index,
                "recognizedTexts": texts,
                "recognitionScores": scores,
                "recognizedBoxes": boxes,
                "durationMs": 0,
                "preprocessing": {
                    "nativePreview": True,
                    "originalSize": [image.width, image.height],
                },
            }
        )
    return page_paths, page_results
