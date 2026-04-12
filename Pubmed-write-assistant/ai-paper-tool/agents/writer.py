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
    """Generates complete medical journal paper: Abstract, Introduction, Methods, Results, Discussion, Conclusion."""

    def __init__(self, llm_service: LLMService):
        super().__init__(
            config=AgentConfig(
                system_prompt=WRITER_SYSTEM_PROMPT,
                max_tokens=16384,
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
        """Parse JSON output from Writer LLM with markdown fence removal and truncation repair."""
        text = raw_text.strip()
        # Strip markdown code block fences
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Writer JSON parse failed, attempting repair. Raw[:200]: {raw_text[:200]!r}")
            data = self._try_repair_json(text)
            logger.warning(f"Writer JSON repair result keys: {list(data.keys())}")
            return data

        logger.info(f"Writer JSON keys returned: {list(data.keys())}")
        return {
            "outline": data.get("outline", ""),
            "abstract": data.get("abstract", ""),
            "introduction": data.get("introduction", ""),
            "methods": data.get("methods", ""),
            "results": data.get("results", ""),
            "discussion": data.get("discussion", ""),
            "conclusion": data.get("conclusion", ""),
        }

    def _try_repair_json(self, text: str) -> dict:
        """Attempt to repair truncated JSON by closing open structures."""
        for suffix in ["}", "]", "}]", "}]}", "}]})", "}]})}]}"]:
            try:
                return json.loads(text + suffix)
            except json.JSONDecodeError:
                continue
        logger.warning("Could not repair JSON in WriterAgent, returning empty dict")
        return {}

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
