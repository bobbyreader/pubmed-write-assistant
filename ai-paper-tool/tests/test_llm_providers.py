"""Tests for LLMService dual-provider routing (Agnes/OpenAI + fallback).

Mocks httpx like test_llm_service.py; no real network calls.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")


def _mock_client(mock_client_cls, json_data):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = json_data
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response
    mock_client_cls.return_value = mock_client
    return mock_client


class TestAgnesProvider:
    @patch("backend.services.llm_service.httpx.Client")
    def test_agnes_call_uses_openai_shape(self, mock_client_cls):
        from backend.services.llm_service import LLMService

        mock_client = _mock_client(mock_client_cls, {
            "choices": [{"message": {"content": "Agnes says hi"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7},
        })
        with patch.dict(os.environ, {
            "LLM_PROVIDER": "agnes",
            "AGNES_API_KEY": "agnes-key",
        }):
            svc = LLMService()
            # Caller passes a MiniMax model name; the Agnes provider must
            # still use its own configured model.
            result = svc.call("sys prompt", "user prompt",
                              model="MiniMax-M2.7-highspeed", max_tokens=64)

        assert result == "Agnes says hi"
        args, kwargs = mock_client.post.call_args
        assert args[0].endswith("/chat/completions")
        payload = kwargs["json"]
        assert payload["model"] == "agnes-3.0-flash"
        assert payload["messages"][0] == {"role": "system", "content": "sys prompt"}
        assert payload["messages"][1] == {"role": "user", "content": "user prompt"}
        assert kwargs["headers"]["Authorization"] == "Bearer agnes-key"

    def test_provider_chain_selection(self):
        from backend.services.llm_service import LLMService

        with patch.dict(os.environ, {"LLM_PROVIDER": "agnes",
                                     "AGNES_API_KEY": "k",
                                     "ANTHROPIC_API_KEY": "a"}):
            svc = LLMService()
            assert [p["name"] for p in svc._providers] == ["openai"]

        with patch.dict(os.environ, {"LLM_PROVIDER": "auto",
                                     "AGNES_API_KEY": "k",
                                     "ANTHROPIC_API_KEY": "a"}):
            svc = LLMService()
            assert [p["name"] for p in svc._providers] == ["openai", "anthropic"]

        with patch.dict(os.environ, {"LLM_PROVIDER": "minimax",
                                     "AGNES_API_KEY": "k",
                                     "ANTHROPIC_API_KEY": "a"}):
            svc = LLMService()
            assert [p["name"] for p in svc._providers] == ["anthropic"]

    def test_raises_when_no_provider_key(self):
        from backend.services.llm_service import LLMService

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "",
                                     "AGNES_API_KEY": "",
                                     "LLM_PROVIDER": "auto"}):
            with pytest.raises(ValueError):
                LLMService()


class TestAutoFallback:
    def test_falls_back_to_minimax_when_agnes_fails(self):
        from backend.services.llm_service import LLMService

        with patch.dict(os.environ, {"LLM_PROVIDER": "auto",
                                     "AGNES_API_KEY": "k",
                                     "ANTHROPIC_API_KEY": "a"}):
            svc = LLMService()

            def fake_call_provider(provider, *args):
                if provider["name"] == "openai":
                    raise RuntimeError("agnes down")
                return ("minimax text", 3, 4)

            with patch.object(LLMService, "_call_provider",
                              side_effect=fake_call_provider):
                result = svc.call("sys", "user")
        assert result == "minimax text"

    def test_raises_when_all_providers_fail(self):
        from backend.services.llm_service import LLMService

        with patch.dict(os.environ, {"LLM_PROVIDER": "auto",
                                     "AGNES_API_KEY": "k",
                                     "ANTHROPIC_API_KEY": "a"}):
            svc = LLMService()
            with patch.object(LLMService, "_call_provider",
                              side_effect=RuntimeError("all down")):
                with pytest.raises(RuntimeError, match="all down"):
                    svc.call("sys", "user")
