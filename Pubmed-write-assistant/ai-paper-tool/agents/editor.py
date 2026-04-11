"""
Editor Agent — revises drafts based on reviewer feedback.
"""

import json
import logging
import re
from typing import Any

from agents.base_agent import AgentConfig, AgentResponse, BaseAgent
from backend.services.llm_service import LLMService
from utils.prompts import EDITOR_SYSTEM_PROMPT, EDITOR_USER_PROMPT

logger = logging.getLogger(__name__)


class EditorAgent(BaseAgent):
    """Revises paper drafts incorporating reviewer suggestions."""

    def __init__(self, llm_service: LLMService):
        super().__init__(
            config=AgentConfig(
                system_prompt=EDITOR_SYSTEM_PROMPT,
                max_tokens=4096,
                temperature=0.4,
            ),
            llm_service=llm_service,
        )

    def get_system_prompt(self) -> str:
        return EDITOR_SYSTEM_PROMPT

    def build_user_prompt(
        self,
        topic: str,
        original_draft: str,
        reviewer_feedback: dict,
        citation_map: dict,
        abstracts_context: str,
    ) -> str:
        citation_map_str = self._format_citation_map(citation_map)
        # Serialize reviewer feedback as formatted string
        feedback_str = json.dumps(reviewer_feedback, indent=2, ensure_ascii=False)
        return EDITOR_USER_PROMPT.format(
            topic=topic,
            original_draft=original_draft,
            reviewer_feedback=feedback_str,
            citation_map_str=citation_map_str,
            abstracts_context=abstracts_context,
        )

    def parse_response(self, raw_text: str) -> dict[str, Any]:
        """Parse JSON editor output."""
        text = raw_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```json?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        data = json.loads(text)
        return {
            "revised_draft": data.get("revised_draft", ""),
            "changes_made": data.get("changes_made", []),
            "unresolved_issues": data.get("unresolved_issues", []),
        }

    def run(
        self,
        topic: str,
        original_draft: str,
        reviewer_feedback: dict,
        citation_map: dict,
        abstracts_context: str,
    ) -> AgentResponse:
        user_prompt = self.build_user_prompt(
            topic, original_draft, reviewer_feedback, citation_map, abstracts_context
        )
        return super().run(user_prompt)

    def _format_citation_map(self, citation_map: dict) -> str:
        lines = []
        for cite_id, meta in citation_map.items():
            lines.append(f"{cite_id}: {meta.get('title', 'N/A')} ({meta.get('year', 'N/A')})")
        return "\n".join(lines)
