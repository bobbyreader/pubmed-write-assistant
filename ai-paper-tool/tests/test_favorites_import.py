"""Tests for research-assistant favorites import (seed literature)."""
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

BACKUP = {
    "app": "pubmed-assistant-v2",
    "kind": "favorites-backup",
    "version": 1,
    "count": 3,
    "favorites": [
        {"pmid": "12345", "title": "Paper One", "authors": ["Smith J", "Lee K"],
         "journal": "Nature", "year": "2024", "doi": "10.1/abc", "pmc": "PMC999",
         "tags": ["x"], "note": "n1"},
        {"pmid": "67890", "title": "Paper Two", "authors": [],
         "journal": "Lancet", "year": "", "doi": ""},
        {"pmid": "12345", "title": "Paper One (dup)", "authors": [],
         "journal": "Nature", "year": "2024"},
    ],
}


class TestParseFavoritesBackup:
    def test_envelope_mapping_and_dedupe(self):
        from backend.services.favorites_import import parse_favorites_backup

        papers = parse_favorites_backup(BACKUP)
        assert len(papers) == 2  # duplicate PMID dropped
        p1 = papers[0]
        assert p1["paperId"] == "12345" and p1["pmid"] == "12345"
        assert p1["title"] == "Paper One"
        assert p1["year"] == 2024 and isinstance(p1["year"], int)
        assert p1["venue"] == "Nature"
        assert p1["authors"] == ["Smith J", "Lee K"]
        assert p1["doi"] == "10.1/abc"
        assert p1["url"] == "https://pubmed.ncbi.nlm.nih.gov/12345/"
        assert papers[1]["year"] is None and papers[1]["doi"] is None

    def test_bare_list_accepted(self):
        from backend.services.favorites_import import parse_favorites_backup

        papers = parse_favorites_backup(BACKUP["favorites"][:1])
        assert len(papers) == 1

    def test_invalid_payloads_raise(self):
        from backend.services.favorites_import import parse_favorites_backup

        with pytest.raises(ValueError):
            parse_favorites_backup({"nope": 1})
        with pytest.raises(ValueError):
            parse_favorites_backup("just a string")
        with pytest.raises(ValueError):
            parse_favorites_backup({"favorites": [{"title": "no pmid"}]})


EFETCH_XML = """<PubmedArticleSet><PubmedArticle><MedlineCitation>
<PMID>12345</PMID><Article><Abstract>
<AbstractText Label="BACKGROUND">Bg text.</AbstractText>
<AbstractText>Main text.</AbstractText>
</Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""


class TestEnrichAbstracts:
    @patch("backend.services.favorites_import.httpx.Client")
    def test_fills_abstracts_from_efetch(self, mock_client_cls):
        from backend.services.favorites_import import enrich_abstracts

        mock_resp = MagicMock()
        mock_resp.text = EFETCH_XML
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        papers = [{"pmid": "12345", "abstract": ""},
                  {"pmid": "67890", "abstract": "already"}]
        out = enrich_abstracts(papers)
        assert out[0]["abstract"] == "BACKGROUND: Bg text. Main text."
        assert out[1]["abstract"] == "already"

    @patch("backend.services.favorites_import.httpx.Client",
           side_effect=RuntimeError("network down"))
    def test_enrichment_failure_is_silent(self, _mock):
        from backend.services.favorites_import import enrich_abstracts

        papers = [{"pmid": "12345", "abstract": ""}]
        assert enrich_abstracts(papers)[0]["abstract"] == ""


class TestRunSeed:
    def test_run_seed_builds_numbered_map(self):
        from agents.researcher import ResearcherAgent

        agent = ResearcherAgent.__new__(ResearcherAgent)
        resp = agent.run_seed([{"title": "A"}, {"title": "B"}])
        assert resp.success is True
        assert list(resp.content["citation_map"].keys()) == ["[1]", "[2]"]

    def test_run_seed_rejects_empty(self):
        from agents.researcher import ResearcherAgent

        agent = ResearcherAgent.__new__(ResearcherAgent)
        assert agent.run_seed([]).success is False


class TestCitationServiceSync:
    def test_set_citation_map_normalizes(self):
        from backend.services.citation_service import CitationService

        svc = CitationService(MagicMock())
        svc.set_citation_map({"[1]": {"title": "T", "abstract": "abs",
                                      "authors": ["A B"], "extra": 1}})
        assert svc.get_all()["[1]"]["title"] == "T"
        assert "abs" in svc.abstracts_context()
        assert "T" in svc.format_for_references()


class TestPipelineSeedPath:
    @patch("workflows.writing_pipeline_with_checkpoint.LLMService")
    @patch("workflows.writing_pipeline_with_checkpoint.SearchService")
    @patch("workflows.writing_pipeline_with_checkpoint.CitationService")
    def test_seeds_skip_search(self, mock_cs, mock_ss, mock_llm):
        from workflows.writing_pipeline_with_checkpoint import (
            WritingPipelineWithCheckpoint,
        )

        seed_result = MagicMock()
        seed_result.success = True
        seed_result.content = {"citation_map": {"[1]": {"title": "Seed"}}}
        write_result = MagicMock()
        write_result.success = False
        write_result.error = "Writer timeout"

        with patch("workflows.writing_pipeline_with_checkpoint.ResearcherAgent") as mock_ra:
            mock_ra.return_value.run_seed.return_value = seed_result
            with patch("workflows.writing_pipeline_with_checkpoint.WriterAgent") as mock_wa:
                mock_wa.return_value.run.return_value = write_result
                with patch("workflows.writing_pipeline_with_checkpoint.ReviewerAgent"):
                    with patch("workflows.writing_pipeline_with_checkpoint.EditorAgent"):
                        pipeline = WritingPipelineWithCheckpoint(enable_checkpoint=False)
                        result = pipeline.run(
                            "topic",
                            seed_papers=[{"title": "Seed", "pmid": "1"}],
                        )

        # Seed path used, search untouched, flow reached the writer.
        mock_ra.return_value.run_seed.assert_called_once()
        mock_ra.return_value.run_search.assert_not_called()
        assert result.success is False
        assert "Writer failed" in result.error
        # CitationService got synced with the citation map.
        mock_cs.return_value.set_citation_map.assert_called_once()
