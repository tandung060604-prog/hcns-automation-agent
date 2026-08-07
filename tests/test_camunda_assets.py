import json
from pathlib import Path
from unittest import TestCase
from xml.etree import ElementTree

from hcns_agent.adapters.camunda7.contract import (
    DMN_QUALITY_INPUT_VARIABLES,
    M4_CLOSED_SET_WORKFLOW_DOCUMENT_TYPES,
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
        self.assertEqual("2.4.0-shadow", process.attrib[_CAMUNDA_VERSION_TAG])

    def test_bpmn_reads_content_before_business_classification_and_extraction(self) -> None:
        root = ElementTree.parse(_BPMN).getroot()
        flows = {
            flow.attrib["id"]: (flow.attrib["sourceRef"], flow.attrib["targetRef"])
            for flow in root.findall(".//bpmn:sequenceFlow", _BPMN_NS)
        }

        self.assertEqual(("GFileValid", "Parse"), flows["F_FileValidDetect"])
        self.assertEqual(("Parse", "GFormat"), flows["F_ParseFormat"])
        self.assertEqual(("GFormat", "OcrRead"), flows["F_FormatImageOcr"])
        self.assertEqual(("GFormat", "NativeRead"), flows["F_FormatNative"])
        self.assertEqual(("GFormat", "RegisterReupload"), flows["F_FormatOther"])
        self.assertEqual(("NativeRead", "Detect"), flows["F_NativeDetect"])
        self.assertEqual(("OcrRead", "Detect"), flows["F_OcrNative"])
        self.assertEqual(("Detect", "GClass"), flows["F_DetectClass"])
        self.assertEqual(("GClass", "Extract"), flows["F_ClassConfirmed"])
        self.assertEqual(("GClass", "ConfirmType"), flows["F_ClassNeedsConfirm"])
        self.assertEqual(("GType", "Extract"), flows["F_TypeConfirmed"])

        mismatch_flow = root.find(
            ".//bpmn:sequenceFlow[@id='F_ClassNeedsConfirm']",
            _BPMN_NS,
        )
        self.assertIsNotNone(mismatch_flow)
        mismatch_condition = mismatch_flow.find("bpmn:conditionExpression", _BPMN_NS)
        self.assertIsNotNone(mismatch_condition)
        self.assertIn("classificationStatus == 'MISMATCH'", mismatch_condition.text)

        parse_task = root.find(".//bpmn:serviceTask[@id='Parse']", _BPMN_NS)
        self.assertIsNotNone(parse_task)
        self.assertEqual("document_parse_content", parse_task.attrib[_CAMUNDA_TOPIC])
        ocr_task = root.find(".//bpmn:serviceTask[@id='OcrRead']", _BPMN_NS)
        self.assertIsNotNone(ocr_task)
        self.assertEqual("document_ocr_read", ocr_task.attrib[_CAMUNDA_TOPIC])
        native_task = root.find(".//bpmn:serviceTask[@id='NativeRead']", _BPMN_NS)
        self.assertIsNotNone(native_task)
        self.assertEqual("document_parse_content", native_task.attrib[_CAMUNDA_TOPIC])

        native_flow = root.find(".//bpmn:sequenceFlow[@id='F_FormatNative']", _BPMN_NS)
        self.assertIsNotNone(native_flow)
        native_condition = native_flow.find("bpmn:conditionExpression", _BPMN_NS)
        self.assertIsNotNone(native_condition)
        self.assertIn("sourceFormat == 'DOCX'", native_condition.text)
        self.assertIn("sourceFormat == 'PDF_TEXT'", native_condition.text)
        gformat = root.find(".//bpmn:exclusiveGateway[@id='GFormat']", _BPMN_NS)
        self.assertIsNotNone(gformat)
        self.assertEqual("F_FormatOther", gformat.attrib["default"])

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

    def test_bpmn_flow_elements_precede_artifacts_for_camunda_713_xsd(self) -> None:
        root = ElementTree.parse(_BPMN).getroot()
        process = root.find(".//bpmn:process", _BPMN_NS)
        self.assertIsNotNone(process)
        child_names = [child.tag.rsplit("}", 1)[-1] for child in process]
        sequence_indexes = [
            index for index, name in enumerate(child_names) if name == "sequenceFlow"
        ]
        artifact_indexes = [
            index
            for index, name in enumerate(child_names)
            if name in {"association", "group", "textAnnotation"}
        ]

        self.assertTrue(sequence_indexes)
        self.assertTrue(artifact_indexes)
        self.assertLess(max(sequence_indexes), min(artifact_indexes))

    def test_bpmn_forms_match_m4_closed_set_and_store_note_references_only(self) -> None:
        root = ElementTree.parse(_BPMN).getroot()
        schema = json.loads(_VARIABLE_SCHEMA.read_text(encoding="utf-8"))
        schema_types = set(schema["$defs"]["workflowDocumentType"]["enum"])
        expected_types = set(M4_CLOSED_SET_WORKFLOW_DOCUMENT_TYPES)
        self.assertLessEqual(expected_types, schema_types)

        type_fields = [
            field
            for field in root.findall(".//camunda:formField", _BPMN_NS)
            if field.attrib.get("id")
            in {"declaredDocumentType", "confirmedDocumentType"}
        ]
        self.assertEqual(3, len(type_fields))
        for field in type_fields:
            with self.subTest(field_id=field.attrib["id"]):
                self.assertEqual(
                    expected_types,
                    {
                        item.attrib["id"]
                        for item in field.findall("camunda:value", _BPMN_NS)
                    },
                )

        form_ids = {
            field.attrib["id"]
            for field in root.findall(".//camunda:formField", _BPMN_NS)
        }
        self.assertIn("hrReviewNoteReference", form_ids)
        self.assertIn("finalHrNoteReference", form_ids)
        self.assertNotIn("hrReviewNote", form_ids)
        self.assertNotIn("finalHrNote", form_ids)

    def test_human_review_is_audited_and_sla_only_escalates(self) -> None:
        root = ElementTree.parse(_BPMN).getroot()
        form_types = {
            field.attrib["type"]
            for field in root.findall(".//camunda:formField", _BPMN_NS)
        }
        self.assertLessEqual(form_types, {"string", "long", "date", "boolean", "enum"})
        flows = {
            flow.attrib["id"]: (flow.attrib["sourceRef"], flow.attrib["targetRef"])
            for flow in root.findall(".//bpmn:sequenceFlow", _BPMN_NS)
        }

        self.assertEqual(
            ("UserReview", "RecordUserReviewAudit"),
            flows["F_UserAudit"],
        )
        self.assertEqual(
            ("HRReview", "RecordHRReviewAudit"),
            flows["F_HRAudit"],
        )
        self.assertEqual(
            ("UserReviewSla", "HRReview"),
            flows["F_UserSlaEscalation"],
        )
        self.assertEqual(
            ("HRReviewSla", "FinalHR"),
            flows["F_HRSlaEscalation"],
        )
        timers = {
            event.attrib["id"]: event.find(
                "bpmn:timerEventDefinition/bpmn:timeDuration",
                _BPMN_NS,
            ).text
            for event in root.findall(".//bpmn:boundaryEvent", _BPMN_NS)
            if event.find("bpmn:timerEventDefinition", _BPMN_NS) is not None
        }
        self.assertEqual({"UserReviewSla": "PT24H", "HRReviewSla": "PT8H"}, timers)
        bpmn_text = _BPMN.read_text(encoding="utf-8")
        self.assertIn("task.getAssignee()", bpmn_text)
        self.assertIn("task.setVariable('reviewedAt'", bpmn_text)
        self.assertNotIn("auto-approve", bpmn_text.casefold())

    def test_dmn_has_safety_inputs_first_hit_policy_and_shadow_gate(self) -> None:
        root = ElementTree.parse(_DMN).getroot()
        decision_table = root.find(".//dmn:decisionTable", _DMN_NS)
        self.assertIsNotNone(decision_table)
        decision = root.find(".//dmn:decision", _DMN_NS)
        self.assertIsNotNone(decision)
        self.assertEqual("2.2.0-shadow", decision.attrib[_CAMUNDA_DMN_VERSION_TAG])
        self.assertEqual("FIRST", decision_table.attrib["hitPolicy"])
        inputs = {
            item.find("dmn:inputExpression/dmn:text", _DMN_NS).text
            for item in decision_table.findall("dmn:input", _DMN_NS)
        }
        self.assertEqual(set(DMN_QUALITY_INPUT_VARIABLES), inputs)
        auto_rule = decision_table.find("dmn:rule[@id='Rule_Auto']", _DMN_NS)
        self.assertIsNotNone(auto_rule)
        auto_inputs = [
            entry.find("dmn:text", _DMN_NS).text
            for entry in auto_rule.findall("dmn:inputEntry", _DMN_NS)
        ]
        self.assertEqual("true", auto_inputs[-1])
        expected_shadow_outputs = {
            "Rule_MissingCritical": '"REQUEST_REUPLOAD"',
            "Rule_Sensitive": '"HR_REVIEW"',
            "Rule_Inconsistency": '"HR_REVIEW"',
            "Rule_QualityReview": '"USER_REVIEW"',
            "Rule_ShadowHighConfidence": '"USER_REVIEW"',
        }
        for rule_id, expected_output in expected_shadow_outputs.items():
            with self.subTest(rule_id=rule_id):
                rule = decision_table.find(f"dmn:rule[@id='{rule_id}']", _DMN_NS)
                self.assertIsNotNone(rule)
                output = rule.find("dmn:outputEntry/dmn:text", _DMN_NS)
                self.assertIsNotNone(output)
                self.assertEqual(expected_output, output.text)
        routing_outputs = {
            output.text.strip('"')
            for output in decision_table.findall(
                "dmn:rule/dmn:outputEntry/dmn:text",
                _DMN_NS,
            )
        }
        self.assertNotIn("MANUAL_REVIEW", routing_outputs)
        self.assertLessEqual(
            routing_outputs,
            {
                "AUTO_CONTINUE",
                "USER_REVIEW",
                "HR_REVIEW",
                "REQUEST_REUPLOAD",
            },
        )

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
