"""Inspection and rasterization ports used before or during parsing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

from hcns_agent.ports.document_parser import DocumentSource

PdfContentProfile: TypeAlias = Literal["native", "scan", "mixed"]


@dataclass(frozen=True, slots=True)
class PdfInspection:
    page_count: int
    has_usable_text: bool
    encrypted: bool = False
    corrupted: bool = False
    content_profile: PdfContentProfile = "scan"


@dataclass(frozen=True, slots=True)
class ImageInspection:
    width: int
    height: int
    media_type: str
    corrupted: bool = False


@dataclass(frozen=True, slots=True)
class RasterizedPage:
    page_index: int
    content: bytes
    width: int
    height: int
    media_type: str = "image/png"


class PdfInspector(Protocol):
    def inspect(self, source: DocumentSource) -> PdfInspection:
        """Inspect a PDF without executing embedded content or following links."""


class ImageInspector(Protocol):
    def inspect(self, source: DocumentSource) -> ImageInspection:
        """Verify image bytes without applying business interpretation."""


class PdfPageRasterizer(Protocol):
    def rasterize(self, source: DocumentSource) -> tuple[RasterizedPage, ...]:
        """Render validated PDF pages into bounded raster images."""
