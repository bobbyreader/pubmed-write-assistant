"""
Reviewer Agent — evaluates drafts and returns structured critique.
"""

import json
import logging
import re
from typing import Any

from agents.base_agent import AgentConfig, AgentResponse, BaseAgent
from backend.services.llm_service import LLMService
from utils.prompts import REVIEWER_SYSTEM_PROMPT, REVIEWER_USER_PROMPT

logger = logging.getLogger(__name__)


class ReviewerAgent(BaseAgent):
    """Reviews paper drafts and provides scored feedback."""

    def __init__(self, llm_service: LLMService):
        super().__init__(
            config=AgentConfig(
                system_prompt=REVIEWER_SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.3,
            ),
            llm_service=llm_service,
        )

    def get_system_prompt(self) -> str:
        return REVIEWER_SYSTEM_PROMPT

    def build_user_prompt(
        self,
        topic: str,
        draft_text: str,
        citation_map: dict,
        abstracts_context: str,
    ) -> str:
        citation_map_str = self._format_citation_map(citation_map)
        return REVIEWER_USER_PROMPT.format(
            topic=topic,
            draft_text=draft_text,
            citation_map_str=citation_map_str,
            abstracts_context=abstracts_context,
        )

    def parse_response(self, raw_text: str) -> dict[str, Any]:
        """Parse JSON review output."""
        # Strip markdown code fences if present
        text = raw_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```json?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        data = json.loads(text)
        return {
            "summary": data.get("summary", ""),
            "score": data.get("score", 5),
            "citation_accuracy_score": data.get("citation_accuracy_score", 10),
            "strengths": data.get("strengths", []),
            "weaknesses": data.get("weaknesses", []),
            "hallucination_flags": data.get("hallucination_flags", []),
            "suggestions": data.get("suggestions", []),
        }

    def run(
        self,
        topic: str,
        draft_text: str,
        citation_map: dict,
        abstracts_context: str,
    ) -> AgentResponse:
        user_prompt = self.build_user_prompt(topic, draft_text, citation_map, abstracts_context)
        return super().run(user_prompt)

    def _format_citation_map(self, citation_map: dict) -> str:
        lines = []
        for cite_id, meta in citation_map.items():
            lines.append(f"{cite_id}: {meta.get('title', 'N/A')} ({meta.get('year', 'N/A')})")
        return "\n".join(lines)
