"""
Writing Pipeline — orchestrates the full Researcher → Writer → Reviewer → Editor workflow.
Implements 2-3 rounds of iteration with early-exit on high scores.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from agents.editor import EditorAgent
from agents.researcher import ResearcherAgent
from agents.reviewer import ReviewerAgent
from agents.writer import WriterAgent
from backend.services.citation_service import CitationService
from backend.services.llm_service import LLMService
from backend.services.rag_service import RAGService
from backend.services.search_service import SearchService

logger = logging.getLogger(__name__)

MAX_ROUNDS = 3
SCORE_EARLY_EXIT = 8.5
SCORE_CITATION_ACCURACY_EXIT = 10.0  # If citations are perfect


@dataclass
class RoundRecord:
    """Records what happened in a single iteration round."""
    round_num: int
    phase: str  # "search" | "write" | "review" | "edit"
    score: float = 0.0
    citation_accuracy_score: float = 10.0
    draft_content: str = ""
    review_content: Any = None
    edit_content: Any = None
    notes: str = ""
    error: str = ""


@dataclass
class PipelineResult:
    """Final result from the full pipeline."""
    success: bool
    final_draft: str = ""
    references: str = ""
    citation_map: dict = field(default_factory=dict)
    rounds: list[RoundRecord] = field(default_factory=list)
    early_exit: bool = False
    error: str = ""


class WritingPipeline:
    """
    Orchestrates the end-to-end paper writing workflow:

    1. Researcher: Search Semantic Scholar → build citation_map
    2. Writer: Generate outline + intro + related work (from citation_map + abstracts)
    3. Reviewer: Evaluate draft → score + suggestions (loop 2-3x)
    4. Editor: Revise draft based on reviewer feedback

    Early exit: If Reviewer score >= 8.5 AND citation_accuracy == 10, stop iterating.
    """

    def __init__(self):
        self.llm_service = LLMService()
        self.search_service = SearchService()
        self.citation_service = CitationService(self.search_service)
        self.rag_service = RAGService(self.citation_service)

        # Initialize agents
        self.researcher = ResearcherAgent(self.llm_service)
        self.writer = WriterAgent(self.llm_service)
        self.reviewer = ReviewerAgent(self.llm_service)
        self.editor = EditorAgent(self.llm_service)

        self.rounds: list[RoundRecord] = []
        self._progress_callback: Optional[Callable[[str, str, float], None]] = None

    def set_progress_callback(self, cb: Callable[[str, str, float], None]):
        """Set a callback for progress updates. cb(phase, message, fraction)."""
        self._progress_callback = cb

    def _emit(self, phase: str, msg: str, fraction: float):
        if self._progress_callback:
            self._progress_callback(phase, msg, fraction)

    def run(
        self,
        topic: str,
        max_rounds: int = MAX_ROUNDS,
        search_top_k: int = 20,
        year_from: int = None,
        year_to: int = None,
        author: str = None,
        venue: str = None,
    ) -> PipelineResult:
        """
        Execute the full pipeline.

        Args:
            topic: Research topic (Chinese or English)
            max_rounds: Maximum Reviewer-Editor iteration rounds (default 3)

        Returns:
            PipelineResult with final_draft, references, citation_map, and round history
        """
        logger.info(f"Starting pipeline for topic: {topic}")
        self.rounds = []

        # ─── Phase 1: Research ───
        self._emit("research", "Searching Semantic Scholar and PubMed...", 0.05)
        try:
            search_result = self.researcher.run_search(
                topic,
                top_k=search_top_k,
                year_from=year_from,
                year_to=year_to,
                author=author,
                venue=venue,
            )
            if not search_result.success:
                return PipelineResult(success=False, error=search_result.error)
            citation_map = search_result.content["citation_map"]
        except Exception as e:
            logger.exception("Research phase failed")
            return PipelineResult(success=False, error=f"Research failed: {e}")

        # Record search round
        search_record = RoundRecord(
            round_num=0,
            phase="search",
            notes=f"Found {len(citation_map)} papers",
        )
        self.rounds.append(search_record)

        self._emit("research", f"Found {len(citation_map)} papers, building context...", 0.15)
        if not citation_map:
            return PipelineResult(
                success=False,
                error="No papers found for this topic. Try different keywords.",
            )

        # Build RAG context
        abstracts_context = self.citation_service.abstracts_context()

        # ─── Phase 2: Write ───
        self._emit("write", "Generating outline, introduction and related work...", 0.20)
        try:
            write_result = self.writer.run(topic, citation_map, abstracts_context)
            if not write_result.success:
                return PipelineResult(
                    success=False,
                    error=f"Writer failed: {write_result.error}",
                    citation_map=citation_map,
                )
            draft_data = write_result.content
            draft_content = self._assemble_draft(topic, draft_data)
        except Exception as e:
            logger.exception("Writer phase failed")
            return PipelineResult(success=False, error=f"Writer failed: {e}")

        write_record = RoundRecord(
            round_num=1,
            phase="write",
            draft_content=draft_content,
        )
        self.rounds.append(write_record)

        # ─── Phase 3: Review + Edit Loop ───
        current_draft = draft_content
        for round_i in range(1, max_rounds + 1):
            logger.info(f"Review round {round_i}/{max_rounds}")
            self._emit("review", f"Reviewing draft (round {round_i}/{max_rounds})...", 0.25 + (round_i - 1) * 0.20)

            # Review
            review_result = self.reviewer.run(
                topic=topic,
                draft_text=current_draft,
                citation_map=citation_map,
                abstracts_context=abstracts_context,
            )

            review_record = RoundRecord(round_num=round_i, phase="review")
            if review_result.success:
                review_data = review_result.content
                review_record.score = review_data.get("score", 5)
                review_record.citation_accuracy_score = review_data.get("citation_accuracy_score", 10)
                review_record.review_content = review_data

                # Hallucination check
                hallucinations = review_data.get("hallucination_flags", [])
                if hallucinations:
                    logger.warning(f"Round {round_i}: hallucinations detected: {hallucinations}")
                    review_record.notes = f"⚠️ Hallucinated citations: {hallucinations}"
            else:
                review_record.error = review_result.error or "Review returned no content"
            self.rounds.append(review_record)

            # Check early exit conditions
            if review_result.success:
                score = review_data.get("score", 0)
                cite_acc = review_data.get("citation_accuracy_score", 0)
                if score >= SCORE_EARLY_EXIT and cite_acc >= SCORE_CITATION_ACCURACY_EXIT:
                    logger.info(f"Early exit at round {round_i}: score={score}, cite_acc={cite_acc}")
                    return PipelineResult(
                        success=True,
                        final_draft=current_draft,
                        references=self.citation_service.format_for_references(),
                        citation_map=citation_map,
                        rounds=self.rounds,
                        early_exit=True,
                    )

            # Edit (unless last round)
            if round_i < max_rounds:
                self._emit("edit", f"Editing and improving (round {round_i}/{max_rounds})...", 0.35 + (round_i - 1) * 0.20)
                edit_result = self.editor.run(
                    topic=topic,
                    original_draft=current_draft,
                    reviewer_feedback=review_record.review_content or {},
                    citation_map=citation_map,
                    abstracts_context=abstracts_context,
                )

                edit_record = RoundRecord(round_num=round_i, phase="edit")
                if edit_result.success:
                    edit_data = edit_result.content
                    current_draft = edit_data.get("revised_draft", current_draft)
                    edit_record.edit_content = edit_data
                    edit_record.notes = f"Changes: {', '.join(edit_data.get('changes_made', [])[:3])}"
                else:
                    edit_record.error = edit_result.error or "Edit returned no content"
                self.rounds.append(edit_record)

        # ─── Final assembly ───
        self._emit("finalize", "Formatting references and finalizing...", 0.98)
        references = self.citation_service.format_for_references()
        logger.info("Pipeline complete")

        return PipelineResult(
            success=True,
            final_draft=current_draft,
            references=references,
            citation_map=citation_map,
            rounds=self.rounds,
            early_exit=False,
        )

    def _assemble_draft(self, topic: str, draft_data: dict) -> str:
        """Assemble full paper markdown from draft_data sections."""
        abstract = draft_data.get("abstract", "")
        introduction = draft_data.get("introduction", "")
        methods = draft_data.get("methods", "")
        results = draft_data.get("results", "")
        discussion = draft_data.get("discussion", "")
        conclusion = draft_data.get("conclusion", "")
        outline = draft_data.get("outline", "")

        parts = [
            f"# {topic}\n",
            f"{outline}\n",
            f"## Abstract\n",
            f"{abstract}\n",
            f"## Introduction\n",
            f"{introduction}\n",
            f"## Methods\n",
            f"{methods}\n",
            f"## Results\n",
            f"{results}\n",
            f"## Discussion\n",
            f"{discussion}\n",
            f"## Conclusion\n",
            f"{conclusion}",
        ]
        return "\n".join(parts)

    def get_history(self) -> list[RoundRecord]:
        """Return the full round history."""
        return self.rounds
