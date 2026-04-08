import asyncio
import unittest

from src.agents.base import AgentMessage, BaseAgent
from src.harness import HarnessLoop


class DummyLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    async def chat(self, system, messages, max_tokens=4096, temperature=0.3):
        return self.responses.pop(0)


class DummyAgent(BaseAgent):
    def _format_input(self, message: AgentMessage) -> str:
        return message.content

    def _parse_output(self, raw_response: str) -> AgentMessage:
        return AgentMessage(role=self.name, content=raw_response, metadata={"approved": raw_response == "done"})


class HarnessTests(unittest.TestCase):
    def test_harness_converges(self):
        agent_a = DummyAgent("a", DummyLLM(["draft", "done"]), "")
        agent_b = DummyAgent("b", DummyLLM(["feedback"]), "")
        loop = HarnessLoop(agent_a, agent_b, max_iterations=3)
        result = asyncio.run(loop.run(AgentMessage(role="user", content="start")))
        self.assertEqual(result.content, "done")
        self.assertTrue(result.metadata["approved"])


if __name__ == "__main__":
    unittest.main()
