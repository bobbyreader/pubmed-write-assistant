"""
LLM Service — unified MiniMax M2.7-highspeed API caller.
Uses httpx for full control over request/response handling.
"""

import os
import logging
from typing import Optional

import httpx
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)
load_dotenv(override=True)

DEFAULT_TIMEOUT = 60


class LLMService:
    """
    Unified LLM calling service for all agents.
    Supports MiniMax M2.7 via Anthropic-compatible endpoint (via local proxy or direct).
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.minimax.chat/v1")
        self.default_model = os.getenv("ANTHROPIC_MODEL", "MiniMax-M2.7-highspeed")
        self._timeout = timeout

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
    ) -> str:
        """
        Call the LLM with a system + user prompt.
        Returns the response text.
        """
        model = model or self.default_model

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

        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(self._url, json=payload, headers=headers)

        resp.raise_for_status()
        data = resp.json()

        # MiniMax may include thinking block — extract text block
        content = data.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        return text
            raise ValueError(f"No text block in response: {data}")
        elif isinstance(content, str):
            return content

        raise ValueError(f"Unexpected response format: {data}")

    def call_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        """
        Streaming call — yields text chunks.
        """
        model = model or self.default_model

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
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
