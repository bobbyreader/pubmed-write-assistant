"""
Researcher Agent — searches Semantic Scholar and builds citation_map.
"""

import json
import logging
from typing import Any

import semanticscholar as ss

from agents.base_agent import AgentConfig, AgentResponse, BaseAgent
from backend.services.llm_service import LLMService
from utils.prompts import (
    RESEARCHER_SYSTEM_PROMPT,
    RESEARCHER_USER_PROMPT,
)

logger = logging.getLogger(__name__)

PAPER_FIELDS = [
    "title", "paperId", "doi", "year", "authors",
    "abstract", "url", "venue", "citationCount",
]


class ResearcherAgent(BaseAgent):
    """Searches academic literature and constructs citation_map."""

    def __init__(self, llm_service: LLMService):
        super().__init__(
            config=AgentConfig(system_prompt=RESEARCHER_SYSTEM_PROMPT),
            llm_service=llm_service,
        )

    def get_system_prompt(self) -> str:
        return RESEARCHER_SYSTEM_PROMPT

    def search(self, topic: str, top_k: int = 10) -> dict[str, dict]:
        """
        Direct Semantic Scholar search (no LLM needed).
        Returns citation_map dict.
        """
        citation_map = {}
        try:
            results = ss.search_paper(topic, limit=top_k)
            for i, paper in enumerate(results, start=1):
                meta = {f: getattr(paper, f, None) for f in PAPER_FIELDS}
                # Flatten authors
                if hasattr(paper, "authors") and paper.authors:
                    meta["authors"] = [a.name for a in paper.authors]
                else:
                    meta["authors"] = []
                citation_map[f"[{i}]"] = meta
        except Exception as e:
            logger.error(f"Semantic Scholar search failed: {e}")
        return citation_map

    def parse_response(self, raw_text: str) -> dict[str, Any]:
        """Parse LLM-structured output from researcher."""
        # The researcher actually does direct search, but the LLM
        # can synthesize/filter. We expect JSON with citation_map + summary.
        data = json.loads(raw_text)
        return {
            "citation_map": data.get("citation_map", {}),
            "summary": data.get("summary", ""),
        }

    def run_search(self, topic: str, top_k: int = 10) -> AgentResponse:
        """
        Main entry point: direct search + optional LLM synthesis.
        For now, direct search is the source of truth.
        """
        citation_map = self.search(topic, top_k=top_k)
        if not citation_map:
            return AgentResponse(
                success=False,
                error="No papers found for this topic. Try different keywords.",
            )
        return AgentResponse(success=True, content={"citation_map": citation_map})
