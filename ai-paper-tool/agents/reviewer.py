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


# Drafts longer than this are reviewed section by section: a single
# whole-draft review call risks truncating its JSON output on long
# round-3 drafts (silently degrading to default scores via JSON repair).
SEGMENT_CHAR_THRESHOLD = 6000
# Per-section prompt cap for the abstracts context (the full citation map
# is always included; abstracts are supporting evidence for cite checks).
SEGMENT_ABSTRACTS_CHARS = 8000
# Max list items kept per section when aggregating (flags are never cut).
SEGMENT_LIST_CAP = 5

SECTION_REVIEW_USER_PROMPT = """## Topic
{topic}

## Section under review: {section_name}

--- SECTION TEXT ---
{section_text}
--- END SECTION TEXT ---

## Citation map (valid citation IDs for this paper)
{citation_map_str}

## Abstracts context (may be truncated)
{abstracts_context}

Review ONLY the section above. Return a single JSON object with keys:
summary, score (0-10), citation_accuracy_score (0-10),
format_compliance_score (0-10), strengths, weaknesses,
hallucination_flags, suggestions.
Be terse: at most 4 items per list, each under 25 words. Output JSON only."""


class ReviewerAgent(BaseAgent):
    """Reviews paper drafts and provides scored feedback."""

    def __init__(self, llm_service: LLMService):
        super().__init__(
            config=AgentConfig(
                system_prompt=REVIEWER_SYSTEM_PROMPT,
                max_tokens=12288,
                temperature=0.3,
                agent_name="reviewer",
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
        """Parse JSON review output with markdown fence removal and truncation repair."""
        text = raw_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```json?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        # Attempt repair if JSON is truncated
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to fix truncated JSON (unclosed strings/arrays)
            data = self._try_repair_json(text)

        return {
            "summary": data.get("summary", ""),
            "score": data.get("score", 5),
            "citation_accuracy_score": data.get("citation_accuracy_score", 10),
            "format_compliance_score": data.get("format_compliance_score", 8),
            "strengths": data.get("strengths", []),
            "weaknesses": data.get("weaknesses", []),
            "hallucination_flags": data.get("hallucination_flags", []),
            "suggestions": data.get("suggestions", []),
        }

    def _try_repair_json(self, text: str) -> dict:
        """Attempt to repair truncated JSON by closing open structures."""
        # Remove trailing incomplete tokens
        lines = text.split("\n")
        repaired_lines = []
        for line in lines:
            # Skip lines with obvious truncation artifacts
            if line.strip().endswith("...") or "Unterminated" in line:
                continue
            repaired_lines.append(line)

        # Try closing the JSON structure
        repaired = "\n".join(repaired_lines)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            # Try appending minimal closing structure
            for suffix in ["}", "]", "}]", "}]}", "}]})"]:
                try:
                    return json.loads(repaired + suffix)
                except json.JSONDecodeError:
                    continue

        logger.warning(f"Could not repair JSON, returning defaults")
        return {}

    def run(
        self,
        topic: str,
        draft_text: str,
        citation_map: dict,
        abstracts_context: str,
    ) -> AgentResponse:
        if len(draft_text or "") > SEGMENT_CHAR_THRESHOLD:
            return self.run_segmented(topic, draft_text, citation_map, abstracts_context)
        user_prompt = self.build_user_prompt(topic, draft_text, citation_map, abstracts_context)
        return super().run(user_prompt)

    # ─── Segmented review ────────────────────────────
    @staticmethod
    def split_sections(draft_text: str) -> list[tuple[str, str]]:
        """
        Split a markdown draft into (section_name, section_text) segments
        on '## ' headers. Text before the first header (title/outline)
        becomes the "Title & Outline" segment. Falls back to one segment.
        """
        sections: list[tuple[str, str]] = []
        current_name = "Title & Outline"
        current_lines: list[str] = []
        for line in (draft_text or "").splitlines():
            if line.startswith("## "):
                if current_lines:
                    sections.append((current_name, "\n".join(current_lines).strip()))
                current_name = line[3:].strip() or "Section"
                current_lines = [line]
            else:
                current_lines.append(line)
        if current_lines:
            sections.append((current_name, "\n".join(current_lines).strip()))
        return [(name, text) for name, text in sections if text] or [
            ("Full Draft", (draft_text or "").strip())
        ]

    def _review_section(
        self,
        topic: str,
        section_name: str,
        section_text: str,
        citation_map: dict,
        abstracts_context: str,
    ) -> AgentResponse:
        user_prompt = SECTION_REVIEW_USER_PROMPT.format(
            topic=topic,
            section_name=section_name,
            section_text=section_text,
            citation_map_str=self._format_citation_map(citation_map),
            abstracts_context=(abstracts_context or "")[:SEGMENT_ABSTRACTS_CHARS],
        )
        return super().run(user_prompt)

    def run_segmented(
        self,
        topic: str,
        draft_text: str,
        citation_map: dict,
        abstracts_context: str,
    ) -> AgentResponse:
        """
        Review a long draft section by section and aggregate the results
        deterministically. Each section call returns a small JSON, so no
        single response can truncate the way a whole-draft review did.
        The aggregated dict has the same shape as parse_response output.
        """
        sections = self.split_sections(draft_text)
        logger.info(f"Segmented review: {len(sections)} sections")

        reviewed: list[tuple[str, dict]] = []
        failed: list[str] = []
        for name, text in sections:
            result = self._review_section(topic, name, text, citation_map, abstracts_context)
            if result.success and isinstance(result.content, dict):
                reviewed.append((name, result.content))
            else:
                failed.append(name)
                logger.warning(f"Section review failed for {name}: {result.error}")

        if not reviewed:
            return AgentResponse(
                success=False,
                error=f"Segmented review failed for all {len(sections)} sections",
            )

        def _avg(key: str, default: float) -> float:
            values = [c[key] for _, c in reviewed if isinstance(c.get(key), (int, float))]
            return round(sum(values) / len(values), 1) if values else default

        def _collect(key: str, cap: int | None) -> list:
            items: list = []
            for name, content in reviewed:
                for item in (content.get(key) or []):
                    items.append(f"[{name}] {item}")
                    if cap is not None and len(items) >= cap * len(reviewed):
                        return items
            return items

        summary_lines = [
            f"Segmented review of {len(reviewed)}/{len(sections)} sections."
        ]
        for name, content in reviewed:
            if content.get("summary"):
                summary_lines.append(f"{name}: {content['summary']}")
        for name in failed:
            summary_lines.append(f"{name}: could not be reviewed (call failed).")

        aggregated = {
            "summary": " ".join(summary_lines),
            "score": _avg("score", 5),
            "citation_accuracy_score": _avg("citation_accuracy_score", 10),
            "format_compliance_score": _avg("format_compliance_score", 8),
            "strengths": _collect("strengths", SEGMENT_LIST_CAP),
            "weaknesses": _collect("weaknesses", SEGMENT_LIST_CAP)
            + [f"[{name}] Section could not be reviewed (call failed)." for name in failed],
            "hallucination_flags": _collect("hallucination_flags", None),
            "suggestions": _collect("suggestions", SEGMENT_LIST_CAP),
            "segmented": True,
            "sections_reviewed": [name for name, _ in reviewed],
        }
        return AgentResponse(success=True, content=aggregated)

    def _format_citation_map(self, citation_map: dict) -> str:
        lines = []
        for cite_id, meta in citation_map.items():
            lines.append(f"{cite_id}: {meta.get('title', 'N/A')} ({meta.get('year', 'N/A')})")
        return "\n".join(lines)
