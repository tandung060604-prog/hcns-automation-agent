import ast
from pathlib import Path
from unittest import TestCase

from hcns_agent.domain.documents import DocumentType, SourceFormat, WorkflowType

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src" / "hcns_agent"
_BANNED_IMPORT_PREFIXES = (
    "hcns_agent.adapters",
    "fitz",
    "pymupdf",
    "openpyxl",
    "PIL",
    "paddleocr",
    "camunda",
    "zeebe",
)


class ArchitectureBoundaryTests(TestCase):
    def test_domain_and_application_do_not_import_adapter_sdks(self) -> None:
        violations: list[str] = []
        for layer in ("domain", "application"):
            for path in (_SRC / layer).glob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    modules: list[str] = []
                    if isinstance(node, ast.Import):
                        modules.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        modules.append(node.module)
                    for module in modules:
                        if module.startswith(_BANNED_IMPORT_PREFIXES):
                            violations.append(f"{path.name}: {module}")
        self.assertEqual([], violations)

    def test_python_long_running_workflow_engine_is_removed(self) -> None:
        self.assertFalse((_SRC / "domain" / "workflow.py").exists())

    def test_three_classifications_are_independent_enum_types(self) -> None:
        self.assertIsNot(SourceFormat, DocumentType)
        self.assertIsNot(DocumentType, WorkflowType)
        self.assertIn("UNKNOWN", SourceFormat.__members__)
        self.assertIn("UNKNOWN", DocumentType.__members__)
        self.assertIn("UNKNOWN", WorkflowType.__members__)

    def test_tests_contain_no_network_client_imports(self) -> None:
        banned = ("requests", "httpx", "urllib.request", "socket")
        violations: list[str] = []
        for path in (_ROOT / "tests").glob("test_*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                else:
                    modules = []
                for module in modules:
                    if module.startswith(banned):
                        violations.append(f"{path.name}: {module}")
        self.assertEqual([], violations)
