"""Tests for Agent JSON parse logic — covers normal + edge cases including truncation repair."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestWriterAgentParse:
    def test_writer_parse_normal_json(self):
        from agents.writer import WriterAgent

        raw = """```json
        {
            "outline": "Introduction and background",
            "abstract": "This study investigates...",
            "introduction": "In recent years...",
            "methods": "We recruited 100 patients...",
            "results": "Results showed...",
            "discussion": "Our findings suggest...",
            "conclusion": "In conclusion..."
        }
        ```"""
        agent = object.__new__(WriterAgent)
        data = agent.parse_response(raw)

        assert data["outline"] == "Introduction and background"
        assert data["abstract"] == "This study investigates..."
        assert data["introduction"] == "In recent years..."
        assert "methods" in data
        assert "results" in data
        assert "discussion" in data
        assert "conclusion" in data

    def test_writer_parse_no_fence(self):
        from agents.writer import WriterAgent

        raw = '{"outline": "A", "abstract": "B", "introduction": "C", "methods": "D", "results": "E", "discussion": "F", "conclusion": "G"}'
        agent = object.__new__(WriterAgent)
        data = agent.parse_response(raw)
        assert data["outline"] == "A"

    def test_writer_parse_truncated_json_single_close(self):
        from agents.writer import WriterAgent

        raw = '{"outline": "Intro'
        agent = object.__new__(WriterAgent)
        result = agent._try_repair_json(raw)
        assert isinstance(result, dict)

    def test_writer_parse_truncated_json_array_suffix(self):
        from agents.writer import WriterAgent

        raw = '{"outline": "Intro", "abstract": "Test'
        agent = object.__new__(WriterAgent)
        result = agent._try_repair_json(raw)
        assert isinstance(result, dict)

    def test_writer_parse_unrecoverable_json(self):
        from agents.writer import WriterAgent

        raw = '{"outline": "Intro'
        agent = object.__new__(WriterAgent)
        result = agent._try_repair_json(raw)
        assert result == {}

    def test_writer_parse_strips_json_fence_with_lang(self):
        from agents.writer import WriterAgent

        raw = """```json
        {"outline": "Title", "abstract": "Abs", "introduction": "Int", "methods": "Met", "results": "Res", "discussion": "Dis", "conclusion": "Con"}
        ```"""
        agent = object.__new__(WriterAgent)
        data = agent.parse_response(raw)
        assert data["outline"] == "Title"

    def test_writer_parse_missing_keys_defaults(self):
        from agents.writer import WriterAgent

        raw = '{"outline": "Only Outline"}'
        agent = object.__new__(WriterAgent)
        data = agent.parse_response(raw)
        assert data["outline"] == "Only Outline"
        assert data["abstract"] == ""


class TestReviewerAgentParse:
    def test_reviewer_parse_normal(self):
        from agents.reviewer import ReviewerAgent

        raw = """{
            "summary": "Good paper overall",
            "score": 7.5,
            "citation_accuracy_score": 9.0,
            "format_compliance_score": 8.0,
            "strengths": ["Clear methodology", "Good structure"],
            "weaknesses": ["Limited sample size"],
            "hallucination_flags": [],
            "suggestions": ["Add more references"]
        }"""
        agent = object.__new__(ReviewerAgent)
        data = agent.parse_response(raw)

        assert data["score"] == 7.5
        assert data["citation_accuracy_score"] == 9.0
        assert data["strengths"] == ["Clear methodology", "Good structure"]
        assert data["hallucination_flags"] == []

    def test_reviewer_parse_with_hallucinations(self):
        from agents.reviewer import ReviewerAgent

        raw = '{"summary": "Test", "score": 6.0, "citation_accuracy_score": 5.0, "format_compliance_score": 7.0, "strengths": [], "weaknesses": ["Bad citations"], "hallucination_flags": ["[99] cited but not in map", "[100] invented"], "suggestions": []}'
        agent = object.__new__(ReviewerAgent)
        data = agent.parse_response(raw)

        assert len(data["hallucination_flags"]) == 2
        assert "[99]" in data["hallucination_flags"][0]

    def test_reviewer_parse_defaults(self):
        from agents.reviewer import ReviewerAgent

        raw = '{"summary": "Minimal"}'
        agent = object.__new__(ReviewerAgent)
        data = agent.parse_response(raw)
        assert data["score"] == 5
        assert data["citation_accuracy_score"] == 10
        assert data["format_compliance_score"] == 8

    def test_reviewer_repair_skips_truncation_artifacts(self):
        from agents.reviewer import ReviewerAgent

        raw = '{"summary": "Test...\n"Unterminated string here'
        agent = object.__new__(ReviewerAgent)
        result = agent._try_repair_json(raw)
        assert isinstance(result, dict)

    def test_reviewer_parse_strips_json_lang(self):
        from agents.reviewer import ReviewerAgent

        raw = """```json
        {"summary": "Has lang", "score": 8, "citation_accuracy_score": 9, "format_compliance_score": 8, "strengths": [], "weaknesses": [], "hallucination_flags": [], "suggestions": []}
        ```"""
        agent = object.__new__(ReviewerAgent)
        data = agent.parse_response(raw)
        assert data["score"] == 8

    def test_reviewer_parse_with_json_lang(self):
        from agents.reviewer import ReviewerAgent

        raw = """```json
        {"summary": "Has lang", "score": 8, "citation_accuracy_score": 9, "format_compliance_score": 8, "strengths": [], "weaknesses": [], "hallucination_flags": [], "suggestions": []}
        ```"""
        agent = object.__new__(ReviewerAgent)
        data = agent.parse_response(raw)
        assert data["score"] == 8


class TestEditorAgentParse:
    def test_editor_parse_normal(self):
        from agents.editor import EditorAgent

        raw = """{
            "revised_draft": "# Revised Paper Title\\n\\nThis is revised content.",
            "changes_made": ["Fixed abstract structure", "Added more citations"],
            "unresolved_issues": []
        }"""
        agent = object.__new__(EditorAgent)
        data = agent.parse_response(raw)

        assert "Revised Paper Title" in data["revised_draft"]
        assert "Fixed abstract" in data["changes_made"][0]
        assert data["unresolved_issues"] == []

    def test_editor_parse_truncated_unclosed_string_returns_none(self):
        from agents.editor import EditorAgent

        raw = '{"revised_draft": "Starts here'
        agent = object.__new__(EditorAgent)
        result = agent._try_repair_json(raw)
        assert result is None

    def test_editor_parse_unrecoverable(self):
        from agents.editor import EditorAgent

        raw = '{"revised_draft": "Starts'
        agent = object.__new__(EditorAgent)
        result = agent._try_repair_json(raw)
        assert result is None

    def test_editor_parse_returns_none_on_failed_repair(self):
        from agents.editor import EditorAgent

        raw = '{"revised_draft": "Partial'
        agent = object.__new__(EditorAgent)
        result = agent.parse_response(raw)
        assert result is None

    def test_editor_parse_defaults(self):
        from agents.editor import EditorAgent

        raw = '{"revised_draft": "Fixed"}'
        agent = object.__new__(EditorAgent)
        data = agent.parse_response(raw)
        assert data["revised_draft"] == "Fixed"
        assert data["changes_made"] == []
        assert data["unresolved_issues"] == []

    def test_editor_parse_strips_json_lang(self):
        from agents.editor import EditorAgent

        raw = """```json
        {"revised_draft": "Clean", "changes_made": [], "unresolved_issues": []}
        ```"""
        agent = object.__new__(EditorAgent)
        data = agent.parse_response(raw)
        assert data["revised_draft"] == "Clean"
