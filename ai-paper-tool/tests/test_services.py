"""Tests for CitationService and RAGService."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCitationServiceFormat:
    def test_format_for_references_multiple_authors(self):
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        cs = CitationService(SearchService())
        cs.citation_map = {
            "[1]": {
                "title": "Deep Learning for Medical Imaging",
                "year": 2022,
                "authors": ["Alice Smith", "Bob Jones", "Carol White", "Dan Brown"],
                "venue": "Nature Medicine",
                "doi": "10.1038/nm.2022",
            }
        }
        refs = cs.format_for_references()
        assert "Alice Smith, Bob Jones, Carol White, et al." in refs
        assert "Deep Learning for Medical Imaging" in refs
        assert "Nature Medicine, 2022" in refs
        assert "10.1038/nm.2022" in refs

    def test_format_for_references_no_doi(self):
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        cs = CitationService(SearchService())
        cs.citation_map = {
            "[1]": {
                "title": "No DOI Paper",
                "year": 2021,
                "authors": ["Single Author"],
                "venue": "Preprint",
                "doi": None,
            }
        }
        refs = cs.format_for_references()
        assert "DOI:" not in refs

    def test_validate_citations_valid(self):
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        cs = CitationService(SearchService())
        cs.citation_map = {"[1]": {}, "[2]": {}, "[3]": {}}

        text = "As shown in [1] and [2], our approach outperforms prior work [3]."
        invalid = cs.validate_citations(text)
        assert invalid == []

    def test_validate_citations_invalid(self):
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        cs = CitationService(SearchService())
        cs.citation_map = {"[1]": {}, "[2]": {}}

        text = "According to [1], [2], and [99], this is novel."
        invalid = cs.validate_citations(text)
        assert "[99]" in invalid

    def test_validate_citations_numeric_extraction(self):
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        cs = CitationService(SearchService())
        cs.citation_map = {"[1]": {}, "[2]": {}, "[3]": {}}

        text = "Multiple [1] citations [2] and [3] here."
        invalid = cs.validate_citations(text)
        assert invalid == []

    def test_get_returns_paper(self):
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        cs = CitationService(SearchService())
        cs.citation_map = {"[1]": {"title": "Paper Title"}}
        paper = cs.get("[1]")
        assert paper["title"] == "Paper Title"

    def test_get_missing_returns_none(self):
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        cs = CitationService(SearchService())
        cs.citation_map = {}
        assert cs.get("[999]") is None

    def test_abstracts_context_format(self):
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        cs = CitationService(SearchService())
        cs.citation_map = {
            "[1]": {"title": "Paper One", "abstract": "This is the abstract of paper one."},
            "[2]": {"title": "Paper Two", "abstract": "Paper two abstract."},
        }
        ctx = cs.abstracts_context()
        assert "[1]" in ctx
        assert "Paper One" in ctx
        assert "abstract of paper one" in ctx


class TestRAGService:
    def test_truncate_abstract_short(self):
        from backend.services.rag_service import RAGService
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        rag = RAGService(CitationService(SearchService()))
        short = "Short abstract."
        assert rag._truncate_abstract(short) == short

    def test_truncate_abstract_long(self):
        from backend.services.rag_service import RAGService
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        rag = RAGService(CitationService(SearchService()))
        long_text = "A" * 1000
        truncated = rag._truncate_abstract(long_text)
        assert len(truncated) <= 1000
        assert len(truncated) < len(long_text)
        assert truncated.endswith("...")

    def test_truncate_abstract_at_word_boundary(self):
        from backend.services.rag_service import RAGService
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        rag = RAGService(CitationService(SearchService()))
        long_text = "A" * 840 + " boundary"
        truncated = rag._truncate_abstract(long_text)
        assert truncated.endswith("...")

    def test_build_writer_context_empty(self):
        from backend.services.rag_service import RAGService
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        rag = RAGService(CitationService(SearchService()))
        ctx = rag.build_writer_context()
        assert "No papers found" in ctx

    def test_build_writer_context_with_papers(self):
        from backend.services.rag_service import RAGService
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        rag = RAGService(CitationService(SearchService()))
        rag.citation_service.citation_map = {
            "[1]": {
                "title": "Test Paper",
                "year": 2023,
                "authors": ["Alice"],
                "abstract": "This is a test abstract that is moderately long.",
            }
        }
        ctx = rag.build_writer_context()
        assert "Test Paper" in ctx
        assert "[1]" in ctx
        assert "Alice" in ctx
        assert "2023" in ctx
        assert "This is a test abstract" in ctx

    def test_build_researcher_context(self):
        from backend.services.rag_service import RAGService
        from backend.services.citation_service import CitationService
        from backend.services.search_service import SearchService

        rag = RAGService(CitationService(SearchService()))
        ctx = rag.build_researcher_context("machine learning in oncology")
        assert "machine learning in oncology" in ctx
