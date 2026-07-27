"""PII-free demonstration of OCR proposal and HITL routing."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from hcns_agent.adapters.mock_ocr import DeterministicMockOcrEngine
from hcns_agent.application.process_document import ProcessDocument
from hcns_agent.domain.models import DocumentType, HrDocument


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    document = HrDocument(
        document_id="SYNTHETIC-HR-0001",
        filename="synthetic-input.png",
        document_type=DocumentType.EMPLOYMENT_CONTRACT,
    )
    proposal = ProcessDocument(DeterministicMockOcrEngine()).execute(document)
    print(json.dumps(asdict(proposal), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
