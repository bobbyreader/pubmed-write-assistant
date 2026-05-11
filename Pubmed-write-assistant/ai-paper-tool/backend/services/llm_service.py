"""
LLM Service — unified MiniMax M2.7-highspeed API caller.
Uses httpx for full control over request/response handling.
Includes metrics tracking for token counting and error monitoring.
"""

import os
import logging
from typing import Optional

import httpx
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

from .metrics_service import APICallRecord, MetricsService, Timer

logger = logging.getLogger(__name__)
load_dotenv(override=True)

DEFAULT_TIMEOUT = 180


class LLMService:
    """
    Unified LLM calling service for all agents.
    Supports MiniMax M2.7 via Anthropic-compatible endpoint (via local proxy or direct).
    Tracks token usage and API call metrics.
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.minimax.chat/v1")
        self.default_model = os.getenv("ANTHROPIC_MODEL", "MiniMax-M2.7-highspeed")
        self._timeout = timeout
        self._metrics = MetricsService()

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set in environment or .env file")

        # Build Anthropic-compatible messages endpoint
        self._url = f"{self.base_url.rstrip('/')}/v1/messages"
        logger.info(f"LLMService initialized with model={self.default_model}, url={self._url}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        agent: str = "unknown",
    ) -> str:
        """
        Call the LLM with a system + user prompt.
        Returns the response text.
        Tracks token usage and call metrics.
        """
        model = model or self.default_model
        timestamp = self._metrics._session_start.isoformat()

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "thinking": {"type": "disabled"},
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Track timing
        with Timer() as timer:
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.post(self._url, json=payload, headers=headers)

                resp.raise_for_status()
                data = resp.json()

                # Extract token usage if available (MiniMax format)
                usage = data.get("usage", {})
                input_tokens = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
                output_tokens = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)

                # MiniMax may include thinking block — extract text block
                content = data.get("content", [])
                text_result = ""
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                text_result = text
                                break
                    if not text_result:
                        raise ValueError(f"No text block in response: {data}")
                elif isinstance(content, str):
                    text_result = content
                else:
                    raise ValueError(f"Unexpected response format: {data}")

                # Log successful call
                record = APICallRecord(
                    timestamp=timestamp,
                    agent=agent,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    duration_ms=timer.duration_ms,
                    success=True,
                    max_tokens_requested=max_tokens,
                )
                self._metrics.log_call(record)

                return text_result

            except Exception as e:
                # Log failed call
                record = APICallRecord(
                    timestamp=timestamp,
                    agent=agent,
                    model=model,
                    duration_ms=timer.duration_ms,
                    success=False,
                    error=str(e),
                    max_tokens_requested=max_tokens,
                )
                self._metrics.log_call(record)
                logger.error(f"LLM call failed for {agent}: {e}")
                raise

    def call_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        agent: str = "unknown",
    ):
        """
        Streaming call — yields text chunks.
        Note: Streaming calls don't track token usage accurately.
        """
        model = model or self.default_model

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "thinking": {"type": "disabled"},
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "stream": True,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self._timeout) as client:
            with client.stream("POST", self._url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            break
                        import json as _json
                        data = _json.loads(chunk)
                        content = data.get("content", [])
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    yield block.get("text", "")

    def get_metrics_summary(self):
        """Get current session metrics summary."""
        return self._metrics.get_session_summary()

    def get_metrics_display(self):
        """Get formatted metrics summary for display."""
        return self._metrics.format_summary_for_display()
