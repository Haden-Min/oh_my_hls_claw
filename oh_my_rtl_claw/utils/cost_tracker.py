from __future__ import annotations

from dataclasses import dataclass, field


class CostLimitExceeded(RuntimeError):
    pass


@dataclass
class CostTracker:
    PRICING: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "gpt-5.4": {"input": 2.50, "output": 10.0},
            "gpt-5.4-mini": {"input": 0.25, "output": 2.0},
            "gpt-5.2": {"input": 1.75, "output": 14.0},
            "gpt-5-mini": {"input": 0.25, "output": 2.0},
            "gpt-5-nano": {"input": 0.05, "output": 0.40},
            "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
            "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
            "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
            "gemma4:26b-it-q4_K_M": {"input": 0.0, "output": 0.0},
            "gemma4:e4b": {"input": 0.0, "output": 0.0},
        }
    )
    warn_threshold: float = 5.0
    hard_limit: float = 20.0
    total_cost: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)

    def record(
        self,
        agent_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        is_oauth_proxy: bool = False,
    ) -> float:
        if is_oauth_proxy:
            cost = 0.0
        else:
            pricing = self.PRICING.get(model, {"input": 5.0, "output": 15.0})
            cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
        self.total_cost += cost
        self.breakdown[agent_name] = self.breakdown.get(agent_name, 0.0) + cost
        if self.total_cost > self.hard_limit:
            raise CostLimitExceeded(f"API cost exceeded ${self.hard_limit:.2f}")
        return cost

    def summary(self) -> dict[str, float | dict[str, float]]:
        return {"total_cost": self.total_cost, "breakdown": dict(self.breakdown)}
