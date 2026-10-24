"""
LLM Service — dual-provider LLM caller with automatic fallback.

Providers:
- "anthropic": MiniMax via Anthropic-compatible /v1/messages (original path).
- "openai":    Agnes AI via OpenAI-compatible /chat/completions.

Provider selection (env LLM_PROVIDER):
- "minimax" (default): MiniMax only — the historical behavior.
- "agnes":             Agnes only (requires AGNES_API_KEY).
- "auto":              Agnes first when AGNES_API_KEY is set, MiniMax as
                       fallback (and vice versa if only MiniMax is set).

Each provider is retried with exponential backoff before falling through to
the next provider in the chain. The public interface (call / call_stream /
metrics) is unchanged for callers.
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

AGNES_DEFAULT_BASE_URL = "https://apihub.agnes-ai.com/v1"
AGNES_DEFAULT_MODEL = "agnes-3.0-flash"


class LLMService:
    """
    Unified LLM calling service for all agents.
    Routes to MiniMax (Anthropic-compatible) and/or Agnes (OpenAI-compatible)
    depending on LLM_PROVIDER, with per-provider retry and cross-provider
    fallback. Tracks token usage and API call metrics.
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self._timeout = timeout
        self._metrics = MetricsService()

        # MiniMax (Anthropic-compatible) configuration — original behavior.
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.minimax.chat/v1")
        self.default_model = os.getenv("ANTHROPIC_MODEL", "MiniMax-M2.7-highspeed")
        self._url = f"{self.base_url.rstrip('/')}/v1/messages"

        # Agnes (OpenAI-compatible) configuration.
        self.agnes_api_key = os.getenv("AGNES_API_KEY")
        self.agnes_base_url = os.getenv("AGNES_BASE_URL", AGNES_DEFAULT_BASE_URL)
        self.agnes_model = os.getenv("AGNES_MODEL", AGNES_DEFAULT_MODEL)
        self._agnes_url = f"{self.agnes_base_url.rstrip('/')}/chat/completions"

        self._providers = self._build_provider_chain()
        if not self._providers:
            raise ValueError(
                "No LLM provider configured: set ANTHROPIC_API_KEY (MiniMax) "
                "and/or AGNES_API_KEY (Agnes) in environment or .env file"
            )
        logger.info(
            "LLMService initialized with providers=%s (minimax model=%s, agnes model=%s)",
            [p["name"] for p in self._providers], self.default_model, self.agnes_model,
        )

    # ─── Provider chain ──────────────────────────────
    def _anthropic_provider(self):
        if not self.api_key:
            return None
        return {"name": "anthropic", "url": self._url,
                "api_key": self.api_key, "model": self.default_model}

    def _openai_provider(self):
        if not self.agnes_api_key:
            return None
        return {"name": "openai", "url": self._agnes_url,
                "api_key": self.agnes_api_key, "model": self.agnes_model}

    def _build_provider_chain(self):
        mode = (os.getenv("LLM_PROVIDER") or "minimax").strip().lower()
        anthropic = self._anthropic_provider()
        openai = self._openai_provider()
        if mode == "agnes":
            return [p for p in [openai] if p]
        if mode == "auto":
            return [p for p in [openai, anthropic] if p]
        # "minimax" and any unknown value keep the historical behavior.
        return [p for p in [anthropic] if p]

    def _effective_model(self, provider, model):
        if provider["name"] == "openai":
            # Callers pass MiniMax model names; the OpenAI provider always
            # uses its own configured model.
            return self.agnes_model
        return model or self.default_model

    # ─── Single-attempt raw calls ────────────────────
    def _raw_call(self, provider, system_prompt, user_prompt, model,
                  max_tokens, temperature):
        """One HTTP attempt against one provider. Returns (text, in_tok, out_tok)."""
        headers = {
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        }
        if provider["name"] == "openai":
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
        else:
            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "thinking": {"type": "disabled"},
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }

        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(provider["url"], json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        usage = data.get("usage", {}) or {}
        input_tokens = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
        output_tokens = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)

        if provider["name"] == "openai":
            choices = data.get("choices") or []
            text_result = ""
            if choices:
                message = choices[0].get("message") or {}
                text_result = message.get("content") or ""
            if not text_result:
                raise ValueError(f"No message content in response: {data}")
            return text_result, input_tokens, output_tokens

        # Anthropic-compatible: extract the text block (MiniMax may also
        # include a thinking block, which is skipped).
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
        return text_result, input_tokens, output_tokens

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _call_provider(self, provider, system_prompt, user_prompt, model,
                       max_tokens, temperature):
        return self._raw_call(provider, system_prompt, user_prompt, model,
                              max_tokens, temperature)

    # ─── Public API ──────────────────────────────────
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
        Tries each configured provider in order (with retries); returns the
        first successful response text. Tracks token usage and call metrics.
        """
        timestamp = self._metrics._session_start.isoformat()
        last_error: Optional[Exception] = None

        for provider in self._providers:
            effective_model = self._effective_model(provider, model)
            with Timer() as timer:
                try:
                    text_result, input_tokens, output_tokens = self._call_provider(
                        provider, system_prompt, user_prompt, effective_model,
                        max_tokens, temperature,
                    )
                except Exception as e:
                    last_error = e
                    self._metrics.log_call(APICallRecord(
                        timestamp=timestamp,
                        agent=agent,
                        model=effective_model,
                        duration_ms=timer.duration_ms,
                        success=False,
                        error=f"[{provider['name']}] {e}",
                        max_tokens_requested=max_tokens,
                    ))
                    logger.error(
                        f"LLM call failed via {provider['name']} for {agent}: {e}"
                    )
                    continue

            self._metrics.log_call(APICallRecord(
                timestamp=timestamp,
                agent=agent,
                model=effective_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                duration_ms=timer.duration_ms,
                success=True,
                max_tokens_requested=max_tokens,
            ))
            return text_result

        raise last_error if last_error is not None else RuntimeError(
            "No LLM provider available"
        )

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
        Streaming call — yields text chunks (MiniMax/Anthropic provider only).
        Note: Streaming calls don't track token usage accurately.
        """
        provider = self._anthropic_provider()
        if provider is None:
            raise NotImplementedError(
                "call_stream requires the MiniMax (anthropic) provider"
            )
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
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self._timeout) as client:
            with client.stream("POST", provider["url"], json=payload, headers=headers) as resp:
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
