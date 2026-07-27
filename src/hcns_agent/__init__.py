"""HCNS automation agent core package."""

from hcns_agent.application.process_document import ProcessDocument
from hcns_agent.bootstrap import build_default_intake, build_default_pipeline
from hcns_agent.domain.documents import DocumentType, SourceFormat, WorkflowType
from hcns_agent.domain.models import HrDocument
from hcns_agent.ports.document_parser import DocumentSource

__all__ = [
    "DocumentSource",
    "DocumentType",
    "HrDocument",
    "ProcessDocument",
    "SourceFormat",
    "WorkflowType",
    "build_default_intake",
    "build_default_pipeline",
]
