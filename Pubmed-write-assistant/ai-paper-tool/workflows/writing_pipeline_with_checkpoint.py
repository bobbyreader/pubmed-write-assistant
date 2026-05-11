"""
Writing Pipeline with Checkpoint Support — orchestrates the full Researcher → Writer → Reviewer → Editor workflow.
Implements 2-3 rounds of iteration with early-exit on high scores.
Supports checkpoint saving for interruption recovery.
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
from backend.services.checkpoint_service import Checkpoint, CheckpointService

logger = logging.getLogger(__name__)

MAX_ROUNDS = 3
SCORE_EARLY_EXIT = 8.5
SCORE_CITATION_ACCURACY_EXIT = 10.0


@dataclass
class RoundRecord:
    """Records what happened in a single iteration round."""
    round_num: int
    phase: str
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
    resumed_from_checkpoint: bool = False


class WritingPipelineWithCheckpoint:
    """
    Orchestrates the end-to-end paper writing workflow with checkpoint support.
    Checkpoints are saved after each phase for interruption recovery.
    """

    def __init__(self, enable_checkpoint: bool = True):
        self.llm_service = LLMService()
        self.search_service = SearchService()
        self.citation_service = CitationService(self.search_service)
        self.rag_service = RAGService(self.citation_service)

        self.researcher = ResearcherAgent(self.llm_service)
        self.writer = WriterAgent(self.llm_service)
        self.reviewer = ReviewerAgent(self.llm_service)
        self.editor = EditorAgent(self.llm_service)

        self.rounds: list[RoundRecord] = []
        self._progress_callback: Optional[Callable[[str, str, float], None]] = None
        self._enable_checkpoint = enable_checkpoint
        self._checkpoint_service: Optional[CheckpointService] = None

    def set_progress_callback(self, cb: Callable[[str, str, float], None]):
        self._progress_callback = cb

    def _emit(self, phase: str, msg: str, fraction: float):
        if self._progress_callback:
            self._progress_callback(phase, msg, fraction)

    def _save_checkpoint(self, topic: str, phase: str, current_round: int, 
                         citation_map: dict, current_draft: str, references: str = ""):
        """Save current state to checkpoint."""
        if not self._enable_checkpoint:
            return
        if self._checkpoint_service is None:
            self._checkpoint_service = CheckpointService(topic)
        checkpoint = Checkpoint(
            topic=topic,
            timestamp=datetime.now().isoformat(),
            current_phase=phase,
            current_round=current_round,
            citation_map=citation_map,
            current_draft=current_draft,
            rounds=[asdict(r) for r in self.rounds],
            references=references,
        )
        self._checkpoint_service.save(checkpoint)

    def _clear_checkpoint(self):
        """Clear checkpoint after successful completion."""
        if self._checkpoint_service:
            self._checkpoint_service.delete()

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
        Execute the full pipeline with optional checkpoint recovery.
        """
        logger.info(f"Starting pipeline for topic: {topic}")
        self.rounds = []
        resumed = False

        # Check for existing checkpoint
        if self._enable_checkpoint:
            checkpoint_svc = CheckpointService(topic)
            existing = checkpoint_svc.load()
            if existing:
                logger.info(f"Found checkpoint: phase={existing.current_phase}, round={existing.current_round}")
                # Ask user or auto-resume
                citation_map = existing.citation_map
                current_draft = existing.current_draft
                self.rounds = [RoundRecord(**r) for r in existing.rounds]
                resumed = True
                abstracts_context = self.citation_service.abstracts_context()

                # Resume from where we left off
                if existing.current_phase == "write":
                    self._emit("write", "Resuming from checkpoint...", 0.20)
                    # Continue to review loop
                    current_phase = "review"
                    start_round = existing.current_round
                elif existing.current_phase in ("review", "edit"):
                    # Continue review loop
                    current_phase = existing.current_phase
                    start_round = existing.current_round
                else:
                    current_phase = existing.current_phase
                    start_round = existing.current_round
            else:
                citation_map = None
                current_draft = None
                current_phase = "research"
                start_round = 0
        else:
            citation_map = None
            current_draft = None
            current_phase = "research"
            start_round = 0

        # ─── Phase 1: Research ───
        if citation_map is None:
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

            search_record = RoundRecord(
                round_num=0,
                phase="search",
                notes=f"Found {len(citation_map)} papers",
            )
            self.rounds.append(search_record)
            self._save_checkpoint(topic, "research", 0, citation_map, "")

        if not citation_map:
            return PipelineResult(
                success=False,
                error="No papers found for this topic. Try different keywords.",
            )

        abstracts_context = self.citation_service.abstracts_context()

        # ─── Phase 2: Write ───
        if current_draft is None:
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
                current_draft = self._assemble_draft(topic, draft_data)
            except Exception as e:
                logger.exception("Writer phase failed")
                return PipelineResult(success=False, error=f"Writer failed: {e}")

            write_record = RoundRecord(
                round_num=1,
                phase="write",
                draft_content=current_draft,
            )
            self.rounds.append(write_record)
            self._save_checkpoint(topic, "write", 1, citation_map, current_draft)

        # ─── Phase 3: Review + Edit Loop ───
        for round_i in range(max(1, start_round), max_rounds + 1):
            logger.info(f"Review round {round_i}/{max_rounds}")
            self._emit("review", f"Reviewing draft (round {round_i}/{max_rounds})...", 0.25 + (round_i - 1) * 0.20)

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
                hallucinations = review_data.get("hallucination_flags", [])
                if hallucinations:
                    logger.warning(f"Round {round_i}: hallucinations detected: {hallucinations}")
                    review_record.notes = f"⚠️ Hallucinated citations: {hallucinations}"
            else:
                review_record.error = review_result.error or "Review returned no content"
            self.rounds.append(review_record)
            self._save_checkpoint(topic, "review", round_i, citation_map, current_draft)

            if review_result.success:
                score = review_data.get("score", 0)
                cite_acc = review_data.get("citation_accuracy_score", 0)
                if score >= SCORE_EARLY_EXIT and cite_acc >= SCORE_CITATION_ACCURACY_EXIT:
                    logger.info(f"Early exit at round {round_i}: score={score}, cite_acc={cite_acc}")
                    self._clear_checkpoint()
                    return PipelineResult(
                        success=True,
                        final_draft=current_draft,
                        references=self.citation_service.format_for_references(),
                        citation_map=citation_map,
                        rounds=self.rounds,
                        early_exit=True,
                        resumed_from_checkpoint=resumed,
                    )

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
                self._save_checkpoint(topic, "edit", round_i, citation_map, current_draft)

        # ─── Final assembly ───
        self._emit("finalize", "Formatting references and finalizing...", 0.98)
        references = self.citation_service.format_for_references()
        self._clear_checkpoint()
        logger.info("Pipeline complete")

        return PipelineResult(
            success=True,
            final_draft=current_draft,
            references=references,
            citation_map=citation_map,
            rounds=self.rounds,
            early_exit=False,
            resumed_from_checkpoint=resumed,
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
        return self.rounds


# Import datetime for checkpoint
from datetime import datetime
from dataclasses import asdict
