"""
Writer Agent — generates paper sections from citation_map and abstracts.
"""

import json
import logging
from typing import Any

from agents.base_agent import AgentConfig, AgentResponse, BaseAgent
from backend.services.llm_service import LLMService
from utils.prompts import WRITER_SYSTEM_PROMPT, WRITER_USER_PROMPT

logger = logging.getLogger(__name__)


class WriterAgent(BaseAgent):
    """Generates paper outline, introduction, and related work."""

    def __init__(self, llm_service: LLMService):
        super().__init__(
            config=AgentConfig(
                system_prompt=WRITER_SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.6,
            ),
            llm_service=llm_service,
        )

    def get_system_prompt(self) -> str:
        return WRITER_SYSTEM_PROMPT

    def build_user_prompt(
        self,
        topic: str,
        citation_map: dict,
        abstracts_context: str,
    ) -> str:
        """Build the user prompt with citation_map and abstracts injected."""
        citation_map_str = self._format_citation_map(citation_map)
        return WRITER_USER_PROMPT.format(
            topic=topic,
            citation_map_str=citation_map_str,
            abstracts_context=abstracts_context,
        )

    def parse_response(self, raw_text: str) -> dict[str, Any]:
        """Parse JSON output from Writer LLM — handles markdown code fences."""
        text = raw_text.strip()
        # Strip markdown code block fences (```json ... ``` or ``` ... ```)
        if text.startswith("```"):
            text = text.split("```")[1] if text.startswith("```") else text
            # Remove language tag after opening fence
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        # Also strip closing ``` if present
        if text.endswith("```"):
            text = text[:-3].strip()
        data = json.loads(text)
        return {
            "outline": data.get("outline", ""),
            "introduction": data.get("introduction", ""),
            "related_work": data.get("related_work", ""),
        }

    def run(self, topic: str, citation_map: dict, abstracts_context: str) -> AgentResponse:
        """
        Generate paper content.
        - topic: research topic
        - citation_map: dict of [N] -> paper metadata
        - abstracts_context: concatenated abstracts from all papers
        """
        user_prompt = self.build_user_prompt(topic, citation_map, abstracts_context)
        return super().run(user_prompt)

    def _format_citation_map(self, citation_map: dict) -> str:
        """Format citation_map for prompt injection."""
        lines = []
        for cite_id, meta in citation_map.items():
            title = meta.get("title", "N/A")
            year = meta.get("year", "N/A")
            authors = meta.get("authors", [])
            if isinstance(authors, list) and authors:
                authors_str = ", ".join(authors[:3])
                if len(authors) > 3:
                    authors_str += " et al."
            else:
                authors_str = "N/A"
            lines.append(f"{cite_id}: {title} ({year}) — {authors_str}")
        return "\n".join(lines)
