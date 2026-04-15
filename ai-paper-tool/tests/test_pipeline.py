"""Tests for WritingPipeline orchestrator — mocks all external dependencies."""
import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestWritingPipeline:
    @patch("workflows.writing_pipeline.LLMService")
    @patch("workflows.writing_pipeline.SearchService")
    @patch("workflows.writing_pipeline.CitationService")
    def test_pipeline_search_no_results_returns_error(self, mock_cs, mock_ss, mock_llm):
        from workflows.writing_pipeline import WritingPipeline

        mock_search_result = MagicMock()
        mock_search_result.success = False
        mock_search_result.error = "No papers found"

        with patch("workflows.writing_pipeline.ResearcherAgent") as mock_ra:
            mock_ra.return_value.run_search.return_value = mock_search_result
            with patch("workflows.writing_pipeline.WriterAgent"):
                with patch("workflows.writing_pipeline.ReviewerAgent"):
                    with patch("workflows.writing_pipeline.EditorAgent"):
                        pipeline = WritingPipeline()
                        result = pipeline.run("nonexistent topic xyz")

        assert result.success is False
        assert "No papers found" in result.error

    @patch("workflows.writing_pipeline.LLMService")
    @patch("workflows.writing_pipeline.SearchService")
    @patch("workflows.writing_pipeline.CitationService")
    def test_pipeline_search_fails_returns_error(self, mock_cs, mock_ss, mock_llm):
        from workflows.writing_pipeline import WritingPipeline

        with patch("workflows.writing_pipeline.ResearcherAgent") as mock_ra:
            mock_ra.return_value.run_search.side_effect = Exception("Network failure")
            with patch("workflows.writing_pipeline.WriterAgent"):
                with patch("workflows.writing_pipeline.ReviewerAgent"):
                    with patch("workflows.writing_pipeline.EditorAgent"):
                        pipeline = WritingPipeline()
                        result = pipeline.run("test topic")

        assert result.success is False
        assert "Research failed" in result.error

    @patch("workflows.writing_pipeline.LLMService")
    @patch("workflows.writing_pipeline.SearchService")
    @patch("workflows.writing_pipeline.CitationService")
    def test_pipeline_writer_fails_returns_error(self, mock_cs, mock_ss, mock_llm):
        from workflows.writing_pipeline import WritingPipeline

        search_result = MagicMock()
        search_result.success = True
        search_result.content = {"citation_map": {"[1]": {"title": "Paper"}}}

        write_result = MagicMock()
        write_result.success = False
        write_result.error = "Writer timeout"

        with patch("workflows.writing_pipeline.ResearcherAgent") as mock_ra:
            mock_ra.return_value.run_search.return_value = search_result
            with patch("workflows.writing_pipeline.WriterAgent") as mock_wa:
                mock_wa.return_value.run.return_value = write_result
                with patch("workflows.writing_pipeline.ReviewerAgent"):
                    with patch("workflows.writing_pipeline.EditorAgent"):
                        pipeline = WritingPipeline()
                        result = pipeline.run("test topic")

        assert result.success is False
        assert "Writer failed" in result.error

    @patch("workflows.writing_pipeline.LLMService")
    @patch("workflows.writing_pipeline.SearchService")
    @patch("workflows.writing_pipeline.CitationService")
    def test_pipeline_assembles_draft_correctly(self, mock_cs, mock_ss, mock_llm):
        from workflows.writing_pipeline import WritingPipeline

        pipeline = WritingPipeline()
        draft_data = {
            "outline": "Outline: I. Background\nII. Methods",
            "abstract": "Abstract: This study...",
            "introduction": "Introduction: In recent years...",
            "methods": "Methods: We recruited...",
            "results": "Results: We found...",
            "discussion": "Discussion: Our findings...",
            "conclusion": "Conclusion: In summary...",
        }

        draft = pipeline._assemble_draft("Test Topic", draft_data)

        assert "Test Topic" in draft
        assert "## Abstract" in draft
        assert "Abstract: This study" in draft
        assert "## Introduction" in draft
        assert "## Methods" in draft
        assert "## Results" in draft
        assert "## Discussion" in draft
        assert "## Conclusion" in draft
        assert "Outline:" in draft

    @patch("workflows.writing_pipeline.LLMService")
    @patch("workflows.writing_pipeline.SearchService")
    @patch("workflows.writing_pipeline.CitationService")
    def test_pipeline_review_round_records_score(self, mock_cs, mock_ss, mock_llm):
        from workflows.writing_pipeline import WritingPipeline

        search_result = MagicMock()
        search_result.success = True
        search_result.content = {"citation_map": {"[1]": {"title": "Paper"}}}

        write_result = MagicMock()
        write_result.success = True
        write_result.content = {
            "outline": "O", "abstract": "A", "introduction": "I",
            "methods": "M", "results": "R", "discussion": "D", "conclusion": "C",
        }

        review_result = MagicMock()
        review_result.success = True
        review_result.content = {
            "score": 7.5,
            "citation_accuracy_score": 9.0,
            "hallucination_flags": ["[99] invented"],
        }

        with patch("workflows.writing_pipeline.ResearcherAgent") as mock_ra:
            mock_ra.return_value.run_search.return_value = search_result
            with patch("workflows.writing_pipeline.WriterAgent") as mock_wa:
                mock_wa.return_value.run.return_value = write_result
                with patch("workflows.writing_pipeline.ReviewerAgent") as mock_rv:
                    mock_rv.return_value.run.return_value = review_result
                    with patch("workflows.writing_pipeline.EditorAgent") as mock_ed:
                        mock_ed.return_value.run.return_value = MagicMock(success=True, content={})
                        pipeline = WritingPipeline()
                        result = pipeline.run("test topic", max_rounds=1)

        assert result.success is True
        assert len(result.rounds) > 0
        review_rounds = [r for r in result.rounds if r.phase == "review"]
        assert len(review_rounds) == 1
        assert review_rounds[0].score == 7.5
        assert "[99]" in review_rounds[0].notes

    @patch("workflows.writing_pipeline.LLMService")
    @patch("workflows.writing_pipeline.SearchService")
    @patch("workflows.writing_pipeline.CitationService")
    def test_pipeline_early_exit_on_high_score(self, mock_cs, mock_ss, mock_llm):
        from workflows.writing_pipeline import WritingPipeline

        search_result = MagicMock()
        search_result.success = True
        search_result.content = {"citation_map": {"[1]": {"title": "Paper"}}}

        write_result = MagicMock()
        write_result.success = True
        write_result.content = {
            "outline": "O", "abstract": "A", "introduction": "I",
            "methods": "M", "results": "R", "discussion": "D", "conclusion": "C",
        }

        review_result = MagicMock()
        review_result.success = True
        review_result.content = {
            "score": 9.0,
            "citation_accuracy_score": 10.0,
            "hallucination_flags": [],
        }

        with patch("workflows.writing_pipeline.ResearcherAgent") as mock_ra:
            mock_ra.return_value.run_search.return_value = search_result
            with patch("workflows.writing_pipeline.WriterAgent") as mock_wa:
                mock_wa.return_value.run.return_value = write_result
                with patch("workflows.writing_pipeline.ReviewerAgent") as mock_rv:
                    mock_rv.return_value.run.return_value = review_result
                    with patch("workflows.writing_pipeline.EditorAgent") as mock_ed:
                        pipeline = WritingPipeline()
                        result = pipeline.run("test topic", max_rounds=3)

        assert result.success is True
        assert result.early_exit is True
        mock_ed.return_value.run.assert_not_called()

    @patch("workflows.writing_pipeline.LLMService")
    @patch("workflows.writing_pipeline.SearchService")
    @patch("workflows.writing_pipeline.CitationService")
    def test_pipeline_progress_callback_all_phases(self, mock_cs, mock_ss, mock_llm):
        from workflows.writing_pipeline import WritingPipeline

        search_result = MagicMock()
        search_result.success = True
        search_result.content = {"citation_map": {"[1]": {"title": "Paper"}}}

        write_result = MagicMock()
        write_result.success = True
        write_result.content = {
            "outline": "O", "abstract": "A", "introduction": "I",
            "methods": "M", "results": "R", "discussion": "D", "conclusion": "C",
        }

        review_result = MagicMock()
        review_result.success = True
        review_result.content = {
            "score": 6.0, "citation_accuracy_score": 8.0, "hallucination_flags": [],
        }

        progress_calls = []

        def capture_cb(phase, msg, fraction):
            progress_calls.append((phase, msg, fraction))

        with patch("workflows.writing_pipeline.ResearcherAgent") as mock_ra:
            mock_ra.return_value.run_search.return_value = search_result
            with patch("workflows.writing_pipeline.WriterAgent") as mock_wa:
                mock_wa.return_value.run.return_value = write_result
                with patch("workflows.writing_pipeline.ReviewerAgent") as mock_rv:
                    mock_rv.return_value.run.return_value = review_result
                    with patch("workflows.writing_pipeline.EditorAgent") as mock_ed:
                        mock_ed.return_value.run.return_value = MagicMock(success=True, content={})
                        pipeline = WritingPipeline()
                        pipeline.set_progress_callback(capture_cb)
                        pipeline.run("test topic", max_rounds=2)

        phases = [p for p, _, _ in progress_calls]
        assert "research" in phases
        assert "write" in phases
        assert "review" in phases
        assert "edit" in phases
