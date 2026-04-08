import asyncio
import unittest

from src.agents.base import AgentMessage
from src.agents.guide_writer import GuideWriterAgent
from src.agents.onboarder import OnboarderAgent
from src.agents.manager import ManagerAgent
from src.agents.planner import PlannerAgent
from src.agents.rtl_designer import RTLDesignerAgent
from src.agents.verifier import VerifierAgent


class DummyLLM:
    def __init__(self, response):
        self.response = response

    async def chat(self, system, messages, max_tokens=4096, temperature=0.3):
        return self.response


class AgentTests(unittest.TestCase):
    def test_planner_parses_spec(self):
        agent = PlannerAgent("planner", DummyLLM('<SPEC>{"architecture_name":"demo","modules":[],"design_steps":[]}</SPEC>'), "")
        result = asyncio.run(agent.send(AgentMessage(role="user", content="x")))
        self.assertEqual(result.artifacts["spec"]["architecture_name"], "demo")

    def test_specialized_agents_parse_expected_tags(self):
        rtl_agent = RTLDesignerAgent("rtl", DummyLLM("<VERILOG>module demo; endmodule</VERILOG><NOTES>ok</NOTES>"), "")
        verifier = VerifierAgent("verifier", DummyLLM("<TESTBENCH>module tb; endmodule</TESTBENCH><CODE_REVIEW>ok</CODE_REVIEW><SCORE>100</SCORE><VERDICT>PASS</VERDICT>"), "")
        onboarding = OnboarderAgent("onboarder", DummyLLM("<CONSTRAINTS>x</CONSTRAINTS><WRAPPER>y</WRAPPER><BUILD_SCRIPT>z</BUILD_SCRIPT>"), "")
        guide = GuideWriterAgent("guide", DummyLLM("<DOCUMENT># Demo</DOCUMENT>"), "")
        rtl_result = asyncio.run(rtl_agent.send(AgentMessage(role="manager", content="x")))
        verify_result = asyncio.run(verifier.send(AgentMessage(role="manager", content="x")))
        onboard_result = asyncio.run(onboarding.send(AgentMessage(role="manager", content="x")))
        guide_result = asyncio.run(guide.send(AgentMessage(role="manager", content="x")))
        self.assertIn("module demo", rtl_result.artifacts["verilog"])
        self.assertTrue(verify_result.metadata["approved"])
        self.assertEqual(onboard_result.artifacts["constraints"], "x")
        self.assertEqual(guide_result.artifacts["document"], "# Demo")

    def test_code_agents_unescape_html_entities(self):
        rtl_agent = RTLDesignerAgent("rtl", DummyLLM("<VERILOG>if (a &lt; b) y &lt;= b;</VERILOG>"), "")
        verifier = VerifierAgent("verifier", DummyLLM("<TESTBENCH>if (a &lt; b) begin y &lt;= b; end</TESTBENCH><SCORE>100</SCORE><VERDICT>PASS</VERDICT>"), "")
        rtl_result = asyncio.run(rtl_agent.send(AgentMessage(role="manager", content="x")))
        verify_result = asyncio.run(verifier.send(AgentMessage(role="manager", content="x")))
        self.assertIn("if (a < b) y <=", rtl_result.artifacts["verilog"])
        self.assertIn("if (a < b) begin y <=", verify_result.artifacts["testbench"])

    def test_manager_normalizes_duplicate_module_steps(self):
        spec = {
            "architecture_name": "alu8",
            "modules": [{"name": "alu8"}],
            "design_steps": [
                {"step": "Define interface", "module": "alu8", "verification_scope": ["ports"]},
                {"step": "Implement logic", "module": "alu8", "verification_scope": ["ops"]},
                {"step": "Create tests", "module": "alu8", "verification_scope": ["tb"]},
            ],
        }
        normalized = ManagerAgent.normalize_execution_plan(spec)
        self.assertEqual(len(normalized["design_steps"]), 1)
        step = normalized["design_steps"][0]
        self.assertEqual(step["step"], 1)
        self.assertEqual(step["module"], "alu8")
        self.assertEqual(step["step_id"], "step_01_alu8")
        self.assertIn("Define interface", step["description"])
        self.assertEqual(step["verification"], ["ports", "ops", "tb"])

    def test_manager_normalizes_scalar_verification_without_splitting_characters(self):
        spec = {
            "architecture_name": "alu8",
            "modules": [{"name": "alu8"}],
            "design_steps": [
                {"step": 1, "module": "alu8", "verification": "Provide test vectors", "deliverables": "RTL file"},
            ],
        }
        normalized = ManagerAgent.normalize_execution_plan(spec)
        step = normalized["design_steps"][0]
        self.assertEqual(step["verification"], ["Provide test vectors"])
        self.assertEqual(step["deliverables"], ["RTL file"])

    def test_manager_uses_real_description_instead_of_numeric_step(self):
        spec = {
            "architecture_name": "regfile",
            "modules": [{"name": "regfile_8x8"}],
            "design_steps": [
                {"step": 1, "step_id": "step_01_regfile_8x8", "module": "regfile_8x8"},
            ],
        }
        normalized = ManagerAgent.normalize_execution_plan(spec)
        step = normalized["design_steps"][0]
        self.assertEqual(step["description"], "step_01_regfile_8x8")


if __name__ == "__main__":
    unittest.main()
