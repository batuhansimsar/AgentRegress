"""
AgentRegress — Gemini Agent
Real Gemini API implementation of BaseAgent.
Supports: gemini-2.5-flash, gemini-2.5-pro, gemini-2.0-flash

API key: Read from GEMINI_API_KEY environment variable. NEVER hardcode.

Usage:
    from agents.gemini_agent import GeminiAgent
    from agents.base_agent import Task, FeedbackMode

    agent = GeminiAgent(model="gemini-2.5-flash")
    result, records = agent.run_repair_loop(
        task=task,
        max_iterations=5,
        feedback_mode=FeedbackMode.BASELINE,
    )
"""

from __future__ import annotations
import os
import time
from typing import Optional

from dotenv import load_dotenv

from agents.base_agent import BaseAgent


# Pricing (USD per 1M tokens) as of 2025 — update when pricing changes
# gemini-2.5-flash: $0.075 input, $0.30 output (non-thinking)
PRICING = {
    "gemini-2.5-flash": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
    "gemini-2.5-pro":   {"input": 1.25 / 1_000_000,  "output": 10.0 / 1_000_000},
    "gemini-2.0-flash": {"input": 0.10 / 1_000_000,  "output": 0.40 / 1_000_000},
    "gemini-1.5-flash": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
}


class GeminiAgent(BaseAgent):
    """
    Gemini-based coding agent using the google-genai Python SDK.

    Install: pip install google-genai
    Set env:  export GEMINI_API_KEY="your-key-here"
    """

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 8192,
    ):
        # Local `.env` support is for development only; `.env` is gitignored.
        # An explicitly exported GEMINI_API_KEY still takes precedence.
        load_dotenv()
        super().__init__(
            api_key=api_key or os.environ.get("GEMINI_API_KEY"),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self.model = model
        self.model_id = f"{model}-{self._get_model_date()}"
        self._client = None

    def _get_model_date(self) -> str:
        """Record date of experiment for reproducibility."""
        import datetime
        return datetime.date.today().isoformat()

    def _get_client(self):
        """Lazily initialize the Gemini client."""
        if self._client is None:
            try:
                from google import genai
            except ImportError:
                raise ImportError(
                    "google-genai not installed. Run: pip install google-genai"
                )
            if not self.api_key:
                raise ValueError(
                    "GEMINI_API_KEY not set. "
                    "Set it with: export GEMINI_API_KEY='your-key'"
                )
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def call_llm(self, prompt: str) -> tuple[str, dict]:
        """
        Call Gemini API and return (response_text, metadata).

        Metadata includes: prompt_tokens, completion_tokens, latency_ms, cost_usd.
        Network errors are raised — let the caller handle retries.
        """
        client = self._get_client()

        t_start = time.time()
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config={
                "temperature": self.temperature,
                "max_output_tokens": self.max_tokens,
            }
        )
        latency_ms = (time.time() - t_start) * 1000

        response_text = response.text or ""

        # Token usage (if available from the response)
        prompt_tokens = None
        completion_tokens = None
        cost_usd = None

        try:
            usage = response.usage_metadata
            if usage:
                prompt_tokens = getattr(usage, "prompt_token_count", None)
                completion_tokens = getattr(usage, "candidates_token_count", None)

                # Estimate cost
                pricing = PRICING.get(self.model, {})
                if prompt_tokens and completion_tokens and pricing:
                    cost_usd = (
                        prompt_tokens * pricing["input"]
                        + completion_tokens * pricing["output"]
                    )
        except Exception:
            pass

        metadata = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": round(latency_ms, 1),
            "cost_usd": cost_usd,
            "model": self.model,
        }

        return response_text, metadata
