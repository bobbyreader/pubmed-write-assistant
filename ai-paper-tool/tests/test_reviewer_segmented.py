"""Tests for ReviewerAgent segmented review (long-draft truncation fix)."""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")


def _agent():
    from agents.reviewer import ReviewerAgent

    return ReviewerAgent(MagicMock())


def _draft(section_bodies: dict[str, str]) -> str:
    parts = ["# Topic\n", "Outline text\n"]
    for name, body in section_bodies.items():
        parts.append(f"## {name}\n")
        parts.append(body + "\n")
    return "\n".join(parts)


def _ok(content):
    from agents.base_agent import AgentResponse

    return AgentResponse(success=True, content=content)


def _fail(error="llm down"):
    from agents.base_agent import AgentResponse

    return AgentResponse(success=False, error=error)


SECTION_CONTENT = {
    "score": 8,
    "citation_accuracy_score": 9,
    "format_compliance_score": 7,
    "summary": "solid",
    "strengths": ["clear"],
    "weaknesses": ["terse"],
    "hallucination_flags": [],
    "suggestions": ["expand"],
}


class TestSplitSections:
    def test_splits_on_h2_headers(self):
        agent = _agent()
        sections = agent.split_sections(_draft({
            "Abstract": "abs body",
            "Introduction": "intro body",
            "Methods": "methods body",
        }))
        names = [name for name, _ in sections]
        assert names == ["Title & Outline", "Abstract", "Introduction", "Methods"]
        assert "intro body" in dict(sections)["Introduction"]

    def test_headerless_draft_is_single_segment(self):
        agent = _agent()
        sections = agent.split_sections("just some text\nmore text")
        assert len(sections) == 1
        assert "just some text" in sections[0][1]


class TestRunDispatch:
    def test_short_draft_uses_single_call(self):
        agent = _agent()
        with patch("agents.base_agent.BaseAgent.run",
                   return_value=_ok(dict(SECTION_CONTENT))) as mock_run:
            resp = agent.run("t", "## Abstract\nshort", {}, "")
        assert resp.success is True
        assert mock_run.call_count == 1

    def test_long_draft_uses_segmented_review(self):
        agent = _agent()
        draft = _draft({
            "Abstract": "a" * 2500,
            "Introduction": "b" * 2500,
            "Methods": "c" * 2500,
        })
        assert len(draft) > 6000
        with patch("agents.base_agent.BaseAgent.run",
                   return_value=_ok(dict(SECTION_CONTENT))) as mock_run:
            resp = agent.run("t", draft, {}, "")
        assert resp.success is True
        # Title & Outline + 3 sections
        assert mock_run.call_count == 4
        assert resp.content["segmented"] is True
        assert resp.content["score"] == 8
        assert resp.content["citation_accuracy_score"] == 9


class TestAggregation:
    def test_averages_and_flag_collection(self):
        agent = _agent()
        draft = _draft({
            "Abstract": "a" * 3000,
            "Methods": "m" * 3000,
        })

        def fake_run(self_, user_prompt, **kwargs):
            if "Section under review: Abstract" in user_prompt:
                return _ok({**SECTION_CONTENT, "score": 6,
                            "hallucination_flags": ["fake cite [99]"]})
            if "Section under review: Methods" in user_prompt:
                return _ok({**SECTION_CONTENT, "score": 10,
                            "hallucination_flags": ["invented stat"]})
            return _ok({**SECTION_CONTENT, "score": 8})

        with patch("agents.base_agent.BaseAgent.run", fake_run):
            resp = agent.run_segmented("t", draft, {}, "")
        assert resp.success is True
        # Sections: Title & Outline (8), Abstract (6), Methods (10) -> mean 8
        assert resp.content["score"] == 8
        flags = resp.content["hallucination_flags"]
        assert len(flags) == 2
        assert any("fake cite" in f and f.startswith("[Abstract]") for f in flags)
        assert set(resp.content["sections_reviewed"]) == {
            "Title & Outline", "Abstract", "Methods"}

    def test_partial_failure_still_aggregates(self):
        agent = _agent()
        draft = _draft({
            "Abstract": "a" * 3000,
            "Methods": "m" * 3000,
        })

        def fake_run(self_, user_prompt, **kwargs):
            if "Section under review: Methods" in user_prompt:
                return _fail()
            return _ok(dict(SECTION_CONTENT))

        with patch("agents.base_agent.BaseAgent.run", fake_run):
            resp = agent.run_segmented("t", draft, {}, "")
        assert resp.success is True
        assert "Methods" not in resp.content["sections_reviewed"]
        assert any("could not be reviewed" in w
                   for w in resp.content["weaknesses"])

    def test_all_sections_fail_returns_failure(self):
        agent = _agent()
        draft = _draft({"Abstract": "a" * 3000, "Methods": "m" * 3000})
        with patch("agents.base_agent.BaseAgent.run", return_value=_fail()):
            resp = agent.run_segmented("t", draft, {}, "")
        assert resp.success is False
