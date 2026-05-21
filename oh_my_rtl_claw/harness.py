from __future__ import annotations

from typing import Callable

from .agents.base import AgentMessage, BaseAgent
from .utils.logger import get_logger


class HarnessLoop:
    def __init__(
        self,
        agent_a: BaseAgent,
        agent_b: BaseAgent,
        max_iterations: int = 5,
        convergence_checker: Callable[[AgentMessage, int], bool] | None = None,
        progress_callback: Callable[[str], None] | None = None,
        return_agent_a_on_agent_b_convergence: bool = False,
    ) -> None:
        self.agent_a = agent_a
        self.agent_b = agent_b
        self.max_iterations = max_iterations
        self.convergence_checker = convergence_checker or self._default_convergence
        self.progress_callback = progress_callback
        self.return_agent_a_on_agent_b_convergence = return_agent_a_on_agent_b_convergence
        self.logger = get_logger()

    async def run(self, initial_message: AgentMessage) -> AgentMessage:
        current_message = initial_message
        response_a = initial_message
        for iteration in range(self.max_iterations):
            if self.progress_callback:
                self.progress_callback(self._format_progress(iteration + 1, self.agent_a.name, "draft" if iteration == 0 else "revision"))
            response_a = await self.agent_a.send(current_message)
            self.logger.info("[Harness] %s iteration %s", self.agent_a.name, iteration + 1)
            if self.convergence_checker(response_a, iteration):
                self.logger.info("[Harness] converged at iteration %s", iteration + 1)
                return response_a
            if self.progress_callback:
                self.progress_callback(self._format_progress(iteration + 1, self.agent_b.name, "review"))
            response_b = await self.agent_b.send(response_a)
            self.logger.info("[Harness] %s feedback iteration %s", self.agent_b.name, iteration + 1)
            current_message = response_b
            if self.convergence_checker(response_b, iteration):
                self.logger.info("[Harness] converged at iteration %s", iteration + 1)
                return response_a if self.return_agent_a_on_agent_b_convergence else response_b
        self.logger.info("[Harness] max iterations reached")
        return response_a

    async def run_from_agent_a_response(self, initial_response_a: AgentMessage) -> AgentMessage:
        response_a = initial_response_a
        for iteration in range(self.max_iterations):
            if self.progress_callback:
                self.progress_callback(self._format_progress(iteration + 1, self.agent_b.name, "review"))
            response_b = await self.agent_b.send(response_a)
            self.logger.info("[Harness] %s feedback iteration %s", self.agent_b.name, iteration + 1)
            if self.convergence_checker(response_b, iteration):
                self.logger.info("[Harness] converged at iteration %s", iteration + 1)
                return response_a if self.return_agent_a_on_agent_b_convergence else response_b

            if iteration == self.max_iterations - 1:
                break

            if self.progress_callback:
                self.progress_callback(self._format_progress(iteration + 2, self.agent_a.name, "revision"))
            response_a = await self.agent_a.send(response_b)
            self.logger.info("[Harness] %s iteration %s", self.agent_a.name, iteration + 2)
            if self.convergence_checker(response_a, iteration + 1):
                self.logger.info("[Harness] converged at iteration %s", iteration + 2)
                return response_a

        self.logger.info("[Harness] max iterations reached")
        return response_a

    @staticmethod
    def _default_convergence(message: AgentMessage, iteration: int) -> bool:
        score = message.metadata.get("score")
        if isinstance(score, (int, float)):
            return score >= 100
        return bool(message.metadata.get("approved", False))

    def _format_progress(self, iteration: int, agent_name: str, phase: str) -> str:
        return f"Harness iteration {iteration}/{self.max_iterations}: {agent_name} {phase}"
