import asyncio
import unittest

from src.agents.base import AgentMessage
from src.agents.guide_writer import GuideWriterAgent
from src.agents.onboarder import OnboarderAgent
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
        verifier = VerifierAgent("verifier", DummyLLM("<TESTBENCH>module tb; endmodule</TESTBENCH><CODE_REVIEW>ok</CODE_REVIEW><VERDICT>PASS</VERDICT>"), "")
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


if __name__ == "__main__":
    unittest.main()
