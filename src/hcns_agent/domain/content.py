"""Traversal helpers for vendor-neutral canonical content."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from hcns_agent.domain.canonical import (
    CanonicalDocument,
    Heading,
    KeyValue,
    ListBlock,
    Paragraph,
    SourceLocation,
    Table,
)


@dataclass(frozen=True, slots=True)
class TextObservation:
    text: str
    source: SourceLocation


def iter_text_observations(document: CanonicalDocument) -> Iterable[TextObservation]:
    for page in document.content.pages:
        for block in page.blocks:
            yield from _block_observations(block)
    for block in document.content.blocks:
        yield from _block_observations(block)
    if document.content.workbook is not None:
        for sheet in document.content.workbook.sheets:
            yield TextObservation(
                text=sheet.name,
                source=SourceLocation(
                    source_reference=document.source.source_reference,
                    sheet_name=sheet.name,
                ),
            )
            for row in sheet.rows:
                for cell in row.cells:
                    if cell.value is not None:
                        yield TextObservation(text=str(cell.value), source=cell.source)


def _block_observations(block: object) -> Iterable[TextObservation]:
    if isinstance(block, (Paragraph, Heading)):
        if block.text.strip():
            yield TextObservation(text=block.text, source=block.source)
    elif isinstance(block, ListBlock):
        for item in block.items:
            if item.strip():
                yield TextObservation(text=item, source=block.source)
    elif isinstance(block, Table):
        for row in block.rows:
            for cell in row.cells:
                if cell.text.strip():
                    yield TextObservation(text=cell.text, source=cell.source)
    elif isinstance(block, KeyValue):
        yield TextObservation(
            text=f"{block.key}: {block.value}",
            source=block.source,
        )
