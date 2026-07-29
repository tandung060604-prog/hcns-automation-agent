import json
from pathlib import Path
from unittest import TestCase
from xml.etree import ElementTree

from hcns_agent.adapters.camunda7.contract import (
    M4_SHADOW_POLICY,
    PROCESS_VARIABLE_WHITELIST,
)
from hcns_agent.adapters.camunda7.handlers import ALL_EXTERNAL_TASK_TOPICS

_ROOT = Path(__file__).resolve().parents[1]
_BPMN = _ROOT / "camunda" / "HR_DOCUMENT_AGENT_MVP_V2.bpmn"
_DMN = _ROOT / "camunda" / "HR_DOCUMENT_QUALITY_ROUTING.dmn"
_VARIABLE_SCHEMA = _ROOT / "schemas" / "camunda_process_variables.schema.json"
_SHADOW_POLICY = _ROOT / "config" / "camunda_m4_shadow_policy.json"
_BPMN_NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "camunda": "http://camunda.org/schema/1.0/bpmn",
}
_DMN_NS = {"dmn": "https://www.omg.org/spec/DMN/20191111/MODEL/"}
_CAMUNDA_TOPIC = "{http://camunda.org/schema/1.0/bpmn}topic"
_CAMUNDA_VERSION_TAG = "{http://camunda.org/schema/1.0/bpmn}versionTag"
_CAMUNDA_DMN_VERSION_TAG = "{http://camunda.org/schema/1.0/dmn}versionTag"


class CamundaAssetContractTests(TestCase):
    def test_bpmn_is_camunda_713_and_uses_expected_external_topics(self) -> None:
        root = ElementTree.parse(_BPMN).getroot()
        self.assertEqual("Camunda Platform", root.attrib["{http://camunda.org/schema/modeler/1.0}executionPlatform"])
        self.assertEqual(
            "7.13.0",
            root.attrib["{http://camunda.org/schema/modeler/1.0}executionPlatformVersion"],
        )
        topics = {
            task.attrib[_CAMUNDA_TOPIC]
            for task in root.findall(".//bpmn:serviceTask", _BPMN_NS)
        }
        self.assertEqual(set(ALL_EXTERNAL_TASK_TOPICS), topics)
        process = root.find(".//bpmn:process", _BPMN_NS)
        self.assertIsNotNone(process)
        self.assertEqual("2.1.0-shadow", process.attrib[_CAMUNDA_VERSION_TAG])

    def test_bpmn_reads_content_before_business_classification_and_extraction(self) -> None:
        root = ElementTree.parse(_BPMN).getroot()
        flows = {
            flow.attrib["id"]: (flow.attrib["sourceRef"], flow.attrib["targetRef"])
            for flow in root.findall(".//bpmn:sequenceFlow", _BPMN_NS)
        }

        self.assertEqual(("GFileValid", "OCR"), flows["F_FileValidDetect"])
        self.assertEqual(("OCR", "Detect"), flows["F_OCRExtract"])
        self.assertEqual(("Detect", "GClass"), flows["F_DetectClass"])
        self.assertEqual(("GClass", "Extract"), flows["F_ClassConfirmed"])
        self.assertEqual(("GType", "Extract"), flows["F_TypeConfirmed"])

        parse_task = root.find(".//bpmn:serviceTask[@id='OCR']", _BPMN_NS)
        self.assertIsNotNone(parse_task)
        self.assertEqual("document_parse_content", parse_task.attrib[_CAMUNDA_TOPIC])

    def test_bpmn_incoming_and_outgoing_references_match_sequence_flows(self) -> None:
        root = ElementTree.parse(_BPMN).getroot()
        flows = {
            flow.attrib["id"]: (flow.attrib["sourceRef"], flow.attrib["targetRef"])
            for flow in root.findall(".//bpmn:sequenceFlow", _BPMN_NS)
        }
        process = root.find(".//bpmn:process", _BPMN_NS)
        self.assertIsNotNone(process)
        for element in process:
            element_id = element.attrib.get("id")
            if not element_id:
                continue
            for incoming in element.findall("bpmn:incoming", _BPMN_NS):
                self.assertEqual(element_id, flows[incoming.text][1])
            for outgoing in element.findall("bpmn:outgoing", _BPMN_NS):
                self.assertEqual(element_id, flows[outgoing.text][0])

    def test_bpmn_forms_include_cv_and_store_note_references_only(self) -> None:
        root = ElementTree.parse(_BPMN).getroot()
        cv_values = root.findall(".//camunda:value[@id='CV']", _BPMN_NS)
        self.assertEqual(3, len(cv_values))
        form_ids = {
            field.attrib["id"]
            for field in root.findall(".//camunda:formField", _BPMN_NS)
        }
        self.assertIn("hrReviewNoteReference", form_ids)
        self.assertIn("finalHrNoteReference", form_ids)
        self.assertNotIn("hrReviewNote", form_ids)
        self.assertNotIn("finalHrNote", form_ids)

    def test_dmn_has_safety_inputs_first_hit_policy_and_shadow_gate(self) -> None:
        root = ElementTree.parse(_DMN).getroot()
        decision_table = root.find(".//dmn:decisionTable", _DMN_NS)
        self.assertIsNotNone(decision_table)
        decision = root.find(".//dmn:decision", _DMN_NS)
        self.assertIsNotNone(decision)
        self.assertEqual("2.1.0-shadow", decision.attrib[_CAMUNDA_DMN_VERSION_TAG])
        self.assertEqual("FIRST", decision_table.attrib["hitPolicy"])
        inputs = {
            item.find("dmn:inputExpression/dmn:text", _DMN_NS).text
            for item in decision_table.findall("dmn:input", _DMN_NS)
        }
        self.assertEqual(
            {
                "qualityStatus",
                "reviewRequired",
                "sensitiveFieldNeedsReview",
                "missingCriticalField",
                "businessInconsistency",
                "requiredFieldsComplete",
                "overallConfidence",
                "autoContinueEnabled",
            },
            inputs,
        )
        auto_rule = decision_table.find("dmn:rule[@id='Rule_Auto']", _DMN_NS)
        self.assertIsNotNone(auto_rule)
        auto_inputs = [
            entry.find("dmn:text", _DMN_NS).text
            for entry in auto_rule.findall("dmn:inputEntry", _DMN_NS)
        ]
        self.assertEqual("true", auto_inputs[-1])

        bpmn_text = _BPMN.read_text(encoding="utf-8")
        self.assertIn("execution.setVariable('autoContinueEnabled', false)", bpmn_text)
        self.assertEqual(
            2,
            bpmn_text.count("execution.setVariable('idempotencyKey'"),
        )
        self.assertIn(
            "execution.setVariable('workflowDocumentType', "
            "execution.getVariable('confirmedDocumentType'))",
            bpmn_text,
        )

    def test_variable_schema_matches_code_whitelist_and_shadow_policy_is_locked_off(self) -> None:
        schema = json.loads(_VARIABLE_SCHEMA.read_text(encoding="utf-8"))
        policy = json.loads(_SHADOW_POLICY.read_text(encoding="utf-8"))

        self.assertEqual(PROCESS_VARIABLE_WHITELIST, frozenset(schema["properties"]))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual("Camunda 7.13", f"Camunda {policy['camundaPlatform']}")
        self.assertEqual(M4_SHADOW_POLICY.policy_id, policy["policyId"])
        self.assertEqual(M4_SHADOW_POLICY.version, policy["version"])
        self.assertEqual(M4_SHADOW_POLICY.mode, policy["mode"])
        self.assertEqual(
            M4_SHADOW_POLICY.auto_continue_enabled,
            policy["autoContinueEnabled"],
        )
        self.assertEqual(
            M4_SHADOW_POLICY.real_side_effects_enabled,
            policy["realSideEffectsEnabled"],
        )
        self.assertEqual(
            0,
            policy["ocrEntryGate"]["maximumBaselineCorrectLosses"],
        )
