"""
Researcher Agent — searches Semantic Scholar and builds citation_map.
"""

import json
import logging
from typing import Any

from agents.base_agent import AgentConfig, AgentResponse, BaseAgent
from backend.services.llm_service import LLMService
from backend.services.search_service import SearchService
from utils.prompts import (
    RESEARCHER_SYSTEM_PROMPT,
    RESEARCHER_USER_PROMPT,
)

logger = logging.getLogger(__name__)


class ResearcherAgent(BaseAgent):
    """Searches academic literature and constructs citation_map."""

    def __init__(self, llm_service: LLMService):
        super().__init__(
            config=AgentConfig(
                system_prompt=RESEARCHER_SYSTEM_PROMPT,
                agent_name="researcher",
            ),
            llm_service=llm_service,
        )
        self._search_service = SearchService()

    def get_system_prompt(self) -> str:
        return RESEARCHER_SYSTEM_PROMPT

    def search(
        self,
        topic: str,
        top_k: int = 20,
        year_from: int = None,
        year_to: int = None,
        author: str = None,
        venue: str = None,
    ) -> dict[str, dict]:
        """
        Direct search via SearchService (SS primary + PubMed fallback).
        Returns citation_map dict.
        """
        citation_map = {}
        try:
            papers = self._search_service.search(
                topic,
                top_k=top_k,
                year_from=year_from,
                year_to=year_to,
                author=author,
                venue=venue,
            )
            for i, paper in enumerate(papers, start=1):
                citation_map[f"[{i}]"] = paper
        except Exception as e:
            logger.error(f"Search failed: {e}")
        return citation_map

    def parse_response(self, raw_text: str) -> dict[str, Any]:
        """Parse LLM-structured output from researcher."""
        data = json.loads(raw_text)
        return {
            "citation_map": data.get("citation_map", {}),
            "summary": data.get("summary", ""),
        }

    def run_search(
        self,
        topic: str,
        top_k: int = 20,
        year_from: int = None,
        year_to: int = None,
        author: str = None,
        venue: str = None,
    ) -> AgentResponse:
        """
        Main entry point: direct search via SearchService.
        """
        citation_map = self.search(topic, top_k=top_k, year_from=year_from, year_to=year_to, author=author, venue=venue)
        if not citation_map:
            return AgentResponse(
                success=False,
                error="No papers found for this topic. Try different keywords.",
            )
        return AgentResponse(success=True, content={"citation_map": citation_map})
