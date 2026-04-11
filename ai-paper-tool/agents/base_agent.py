"""
Base Agent class — all agents inherit from this.
Provides unified LLMService access and common utilities.
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.services.llm_service import LLMService

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for an agent instance."""
    system_prompt: str
    model: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7


@dataclass
class AgentResponse:
    """Standard response from any agent."""
    success: bool
    content: Any = None
    error: Optional[str] = None
    raw: Optional[str] = None


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    Subclasses must implement:
    - get_system_prompt() -> str
    - parse_response(raw_text: str) -> Any
    """

    def __init__(self, config: AgentConfig, llm_service: LLMService):
        self.config = config
        self.llm = llm_service
        self._system_prompt_cache: Optional[str] = None

    @property
    def system_prompt(self) -> str:
        """Lazily loaded system prompt."""
        if self._system_prompt_cache is None:
            self._system_prompt_cache = self.get_system_prompt()
        return self._system_prompt_cache

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the agent's system prompt."""
        pass

    @abstractmethod
    def parse_response(self, raw_text: str) -> Any:
        """Parse raw LLM output into structured data."""
        pass

    def run(self, user_prompt: str, **kwargs) -> AgentResponse:
        """
        Execute the agent: call LLM → parse → return structured response.
        """
        try:
            raw = self.llm.call(
                system_prompt=self.system_prompt,
                user_prompt=user_prompt,
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
            parsed = self.parse_response(raw)
            return AgentResponse(success=True, content=parsed, raw=raw)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in {self.__class__.__name__}: {e}")
            return AgentResponse(success=False, error=f"Failed to parse response: {e}", raw=raw)
        except Exception as e:
            logger.exception(f"Agent {self.__class__.__name__} failed")
            return AgentResponse(success=False, error=str(e))

    def _format_citation_map(self, citation_map: dict) -> str:
        """Format citation_map as a readable string for prompts."""
        lines = []
        for cite_id, meta in citation_map.items():
            lines.append(
                f"{cite_id}: {meta.get('title', 'N/A')} "
                f"({meta.get('year', 'N/A')}) - {meta.get('authors', ['N/A'])}"
            )
        return "\n".join(lines)
