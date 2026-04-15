"""Tests for SearchService — mocks httpx to test OpenAlex/PubMed/SS parsing."""
import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.search_service import SearchService, _reconstruct_abstract


class TestReconstructAbstract:
    def test_empty_index_returns_not_available(self):
        assert _reconstruct_abstract({}) == "Abstract not available."

    def test_none_index(self):
        assert _reconstruct_abstract(None) == "Abstract not available."

    def test_normal_index(self):
        idx = {"hello": [0], "world": [1]}
        result = _reconstruct_abstract(idx)
        assert "hello" in result
        assert "world" in result

    def test_out_of_order_index(self):
        idx = {"apple": [2], "banana": [0], "cherry": [1]}
        result = _reconstruct_abstract(idx)
        assert result.index("banana") < result.index("cherry") < result.index("apple")


class TestOpenAlexSearch:
    @patch("backend.services.search_service.httpx.Client")
    def test_openalex_returns_parsed_papers(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{
                "id": "https://openalex.org/W300123",
                "title": "Test Paper Title",
                "doi": "https://doi.org/10.1234/test",
                "publication_year": 2023,
                "abstract_inverted_index": {"test": [0], "abstract": [1]},
                "authorships": [{"author": {"display_name": "Alice Smith"}}, {"author": {"display_name": "Bob Jones"}}],
                "primary_location": {"source": {"display_name": "Nature"}},
                "open_access": {"is_oa": True},
            }]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        svc = SearchService()
        papers = svc._openalex_search("test query", 10, None, None, None, None)

        assert len(papers) == 1
        assert papers[0]["title"] == "Test Paper Title"
        assert papers[0]["year"] == 2023
        assert papers[0]["authors"] == ["Alice Smith", "Bob Jones"]
        assert papers[0]["venue"] == "Nature"
        assert papers[0]["doi"] == "10.1234/test"
        assert papers[0]["abstract"] == "test abstract"

    @patch("backend.services.search_service.httpx.Client")
    def test_openalex_429_returns_empty(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        svc = SearchService()
        papers = svc._openalex_search("test", 10, None, None, None, None)
        assert papers == []

    @patch("backend.services.search_service.httpx.Client")
    def test_openalex_exception_returns_empty(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = Exception("Network error")
        mock_client_cls.return_value = mock_client

        svc = SearchService()
        papers = svc._openalex_search("test", 10, None, None, None, None)
        assert papers == []

    @patch("backend.services.search_service.httpx.Client")
    def test_openalex_year_filter_range(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        svc = SearchService()
        svc._openalex_search("cancer", 10, 2020, 2024, None, None)

        call_args = mock_client.get.call_args
        params = call_args.kwargs.get("params", {})
        assert "filter" in params
        assert "publication_year:2020-2024" in params["filter"]

    @patch("backend.services.search_service.httpx.Client")
    def test_openalex_year_from_only(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        svc = SearchService()
        svc._openalex_search("cancer", 10, 2020, None, None, None)

        call_args = mock_client.get.call_args
        params = call_args.kwargs.get("params", {})
        assert "publication_year:>2019" in params["filter"]

    @patch("backend.services.search_service.httpx.Client")
    def test_openalex_year_to_only(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        svc = SearchService()
        svc._openalex_search("cancer", 10, None, 2020, None, None)

        call_args = mock_client.get.call_args
        params = call_args.kwargs.get("params", {})
        assert "publication_year:<2021" in params["filter"]


class TestPubMedSearch:
    @patch("backend.services.search_service.httpx.Client")
    def test_pubmed_search_returns_parsed_papers(self, mock_client_cls):
        mock_search_resp = MagicMock()
        mock_search_resp.status_code = 200
        mock_search_resp.json.return_value = {"esearchresult": {"idlist": ["12345678"]}}

        xml_body = """<?xml version="1.0"?>
        <PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation>
              <PMID>12345678</PMID>
              <Article>
                <ArticleTitle>Test Article</ArticleTitle>
                <Abstract><AbstractText>Test abstract content.</AbstractText></Abstract>
                <Journal>
                  <Title>Test Journal</Title>
                </Journal>
                <PubDate>
                  <Year>2023</Year>
                </PubDate>
                <AuthorList>
                  <Author>
                    <LastName>Doe</LastName>
                    <ForeName>John</ForeName>
                  </Author>
                </AuthorList>
              </Article>
            </MedlineCitation>
          </PubmedArticle>
        </PubmedArticleSet>"""

        mock_fetch_resp = MagicMock()
        mock_fetch_resp.status_code = 200
        mock_fetch_resp.text = xml_body

        def client_get_side_effect(url, **kwargs):
            if "esearch" in url:
                return mock_search_resp
            return mock_fetch_resp

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = client_get_side_effect
        mock_client_cls.return_value = mock_client

        svc = SearchService()
        papers = svc._pubmed_search("cancer", 10, None, None, None, None)

        assert len(papers) == 1
        assert papers[0]["title"] == "Test Article"
        assert papers[0]["year"] == 2023
        assert papers[0]["venue"] == "Test Journal"
        assert "John Doe" in papers[0]["authors"]
        assert papers[0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/12345678/"

    @patch("backend.services.search_service.httpx.Client")
    def test_pubmed_empty_results(self, mock_client_cls):
        mock_search_resp = MagicMock()
        mock_search_resp.status_code = 200
        mock_search_resp.json.return_value = {"esearchresult": {"idlist": []}}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_search_resp
        mock_client_cls.return_value = mock_client

        svc = SearchService()
        papers = svc._pubmed_search("nonexistent topic xyz", 10, None, None, None, None)
        assert papers == []


class TestSemanticScholarSearch:
    @patch("backend.services.search_service.httpx.Client")
    def test_semantic_scholar_returns_parsed_papers(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{
                "paperId": "SS123",
                "title": "Semantic Scholar Paper",
                "abstract": "This is a test abstract from SS.",
                "year": 2022,
                "venue": "arXiv",
                "authors": [{"name": "Alice"}, {"name": "Bob"}],
                "citationCount": 50,
                "externalIds": {"DOI": "10.1234/ss"},
                "url": "https://example.com/paper",
            }]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        svc = SearchService()
        papers = svc._semantic_scholar_search("test", 10, None, None, None, None)

        assert len(papers) == 1
        assert papers[0]["title"] == "Semantic Scholar Paper"
        assert papers[0]["year"] == 2022
        assert papers[0]["doi"] == "10.1234/ss"
        assert papers[0]["citationCount"] == 50

    @patch("backend.services.search_service.httpx.Client")
    def test_semantic_scholar_429_returns_empty(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        svc = SearchService()
        papers = svc._semantic_scholar_search("test", 10, None, None, None, None)
        assert papers == []


class TestSearchServiceIntegration:
    @patch("backend.services.search_service.httpx.Client")
    def test_search_falls_back_to_pubmed_when_openalex_empty(self, mock_client_cls):
        def json_side_effect():
            call_count = [0]
            def next_json():
                call_count[0] += 1
                if call_count[0] == 1:
                    return {"results": [{"id": "W1", "title": "One Paper", "doi": None, "publication_year": 2020, "abstract_inverted_index": {}, "authorships": [], "primary_location": {}, "open_access": {}}]}
                elif call_count[0] == 2:
                    return {"data": []}
                return {"esearchresult": {"idlist": ["11111111"]}}
            return next_json

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json_side_effect()

        xml_body = """<?xml version="1.0"?>
        <PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation>
              <PMID>11111111</PMID>
              <Article>
                <ArticleTitle>PubMed Fallback Paper</ArticleTitle>
                <Abstract><AbstractText>From PubMed.</AbstractText></Abstract>
                <Journal><Title>PubMed Journal</Title></Journal>
                <PubDate><Year>2021</Year></PubDate>
                <AuthorList/>
              </Article>
            </MedlineCitation>
          </PubmedArticle>
        </PubmedArticleSet>"""
        mock_fetch_resp = MagicMock()
        mock_fetch_resp.status_code = 200
        mock_fetch_resp.text = xml_body

        def client_get_side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "esearch" in url:
                resp.json.return_value = {"esearchresult": {"idlist": ["11111111"]}}
            elif "efetch" in url:
                resp.text = xml_body
            else:
                resp.json.side_effect = json_side_effect()
            return resp

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = client_get_side_effect
        mock_client_cls.return_value = mock_client

        svc = SearchService()
        papers = svc.search("rare topic", top_k=10)
        assert len(papers) >= 1
