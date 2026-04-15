"""Tests for LLMService — mocks httpx to test MiniMax API calling and parsing."""
import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["ANTHROPIC_BASE_URL"] = "https://api.minimax.chat/v1"


class TestLLMServiceCall:
    @patch("backend.services.llm_service.httpx.Client")
    def test_call_returns_text_from_text_block(self, mock_client_cls):
        from backend.services.llm_service import LLMService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "This is the generated text response."}]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        svc = LLMService()
        result = svc.call("You are a helpful assistant.", "What is 2+2?", max_tokens=100)
        assert result == "This is the generated text response."

        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["model"] == "MiniMax-M2.7-highspeed"
        assert payload["max_tokens"] == 100
        assert payload["temperature"] == 0.7

    @patch("backend.services.llm_service.httpx.Client")
    def test_call_raises_on_no_text_block(self, mock_client_cls):
        from backend.services.llm_service import LLMService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"content": [{"type": "thinking", "text": "reasoning..."}]}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        svc = LLMService()
        with pytest.raises(ValueError, match="No text block"):
            svc.call("sys", "user")

    @patch("backend.services.llm_service.httpx.Client")
    def test_call_handles_string_content(self, mock_client_cls):
        from backend.services.llm_service import LLMService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"content": "Direct string response"}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        svc = LLMService()
        result = svc.call("sys", "user")
        assert result == "Direct string response"

    @patch("backend.services.llm_service.httpx.Client")
    def test_call_with_custom_model(self, mock_client_cls):
        from backend.services.llm_service import LLMService

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"content": [{"type": "text", "text": "response"}]}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        svc = LLMService()
        svc.call("sys", "user", model="custom-model", max_tokens=500, temperature=0.9)

        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["model"] == "custom-model"
        assert payload["max_tokens"] == 500
        assert payload["temperature"] == 0.9

    @patch("backend.services.llm_service.httpx.Client")
    def test_call_raises_on_non_200(self, mock_client_cls):
        from backend.services.llm_service import LLMService

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("HTTP 500")

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        svc = LLMService()
        with pytest.raises(Exception):
            svc.call("sys", "user")


class TestLLMServiceNoApiKey:
    def test_raises_if_no_api_key(self):
        old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                from backend.services.llm_service import LLMService
                LLMService()
        finally:
            if old_key:
                os.environ["ANTHROPIC_API_KEY"] = old_key
