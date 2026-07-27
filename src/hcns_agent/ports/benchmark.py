"""Ports used by the offline benchmark runner."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from hcns_agent.domain.understanding import IdpResult
from hcns_agent.ports.document_parser import DocumentSource


class BenchmarkBackend(Protocol):
    @property
    def name(self) -> str:
        """Stable backend identifier."""

    @property
    def version(self) -> str:
        """Installed backend version."""

    @property
    def model_identifiers(self) -> tuple[str, ...]:
        """Pinned model identifiers used by this run."""

    def process(
        self,
        source: DocumentSource,
        *,
        source_path: Path,
        output_directory: Path,
    ) -> IdpResult:
        """Process one authorized source without business side effects."""


class SourcePageCounter(Protocol):
    def count_pages(self, source: DocumentSource) -> int:
        """Count physical PDF/image pages without interpreting their content."""
