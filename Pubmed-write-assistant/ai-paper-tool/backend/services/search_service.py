"""
Search Service — paper search with Semantic Scholar (primary) and PubMed (fallback).
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

SS_FIELDS = [  # valid for paper/search endpoint
    "title", "paperId", "year", "authors",
    "abstract", "citationCount", "venue", "externalIds",
]
PAPER_FIELDS = [  # full set for paper/detail endpoint
    "title", "paperId", "doi", "year", "authors",
    "abstract", "url", "venue", "citationCount",
]

DEFAULT_TIMEOUT = 15
SS_BASE = "https://api.semanticscholar.org/graph/v1"
PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class SearchService:
    """Searches papers using Semantic Scholar (primary) with PubMed fallback."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self._timeout = timeout

    def search(
        self,
        query: str,
        top_k: int = 10,
        year_range: Optional[str] = None,
    ) -> list[dict]:
        """
        Search for papers and return list of paper dicts.
        Tries Semantic Scholar first, falls back to PubMed on 429 or error.
        """
        papers = self._ss_search(query, top_k, year_range)
        if papers:
            return papers
        logger.warning(f"Semantic Scholar unavailable, falling back to PubMed for: {query}")
        return self._pubmed_search(query, top_k)

    def _ss_search(
        self,
        query: str,
        top_k: int,
        year_range: Optional[str],
    ) -> list[dict]:
        """Search via Semantic Scholar Graph API."""
        params = {
            "query": query,
            "limit": min(top_k, 100),
            "fields": ",".join(SS_FIELDS),
        }
        if year_range:
            params["year"] = year_range
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(f"{SS_BASE}/paper/search", params=params)
            if resp.status_code == 429:
                logger.warning("Semantic Scholar rate limit (429)")
                return []
            resp.raise_for_status()
            data = resp.json()
            papers = []
            for item in data.get("data", []):
                ext_ids = item.get("externalIds", {}) or {}
                papers.append({
                    "paperId": item.get("paperId"),
                    "title": item.get("title"),
                    "abstract": item.get("abstract") or "Abstract not available.",
                    "year": item.get("year"),
                    "venue": item.get("venue"),
                    "authors": [a.get("name", "") for a in item.get("authors", [])] if item.get("authors") else [],
                    "citationCount": item.get("citationCount"),
                    "doi": ext_ids.get("DOI"),
                    "url": f"https://www.semanticscholar.org/paper/{item.get('paperId')}" if item.get("paperId") else None,
                })
            logger.info(f"SS returned {len(papers)} papers for: {query}")
            return papers
        except Exception as e:
            logger.error(f"SS search failed: {type(e).__name__}: {e}")
            return []

    def _pubmed_search(self, query: str, top_k: int) -> list[dict]:
        """Search via PubMed E-utilities as fallback."""
        try:
            # Step 1: search for IDs
            with httpx.Client(timeout=self._timeout) as client:
                search_resp = client.get(
                    f"{PUBMED_BASE}/esearch.fcgi",
                    params={"db": "pubmed", "term": query, "retmax": top_k, "retmode": "json"},
                )
            search_resp.raise_for_status()
            search_data = search_resp.json()
            ids = search_data.get("esearchresult", {}).get("idlist", [])
            if not ids:
                logger.info(f"PubMed returned 0 papers for: {query}")
                return []

            # Step 2: fetch details
            id_str = ",".join(ids)
            with httpx.Client(timeout=self._timeout) as client:
                fetch_resp = client.get(
                    f"{PUBMED_BASE}/efetch.fcgi",
                    params={"db": "pubmed", "id": id_str, "retmode": "xml"},
                )
            fetch_resp.raise_for_status()

            papers = self._parse_pubmed_xml(fetch_resp.text, ids)
            logger.info(f"PubMed returned {len(papers)} papers for: {query}")
            return papers
        except Exception as e:
            logger.error(f"PubMed search failed: {type(e).__name__}: {e}")
            return []

    def _parse_pubmed_xml(self, xml_text: str, ids: list[str]) -> list[dict]:
        """Parse PubMed XML into paper dicts."""
        papers = []
        try:
            from xml.etree import ElementTree as ET
            root = ET.fromstring(xml_text)
            ns = {"pm": "http://www.ncbi.nlm.nih.gov NCBI/Pubmed"}
            for article in root.findall(".//pm:PubmedArticle", ns) or root.findall(".//PubmedArticle"):
                pmid_el = article.find(".//pm:PMID", ns) or article.find(".//PMID")
                title_el = article.find(".//pm:ArticleTitle", ns) or article.find(".//ArticleTitle")
                abstract_el = article.find(".//pm:AbstractText", ns) or article.find(".//AbstractText")
                year_el = article.find(".//pm:PubDate/pm:Year", ns) or article.find(".//PubDate/Year")
                journal_el = article.find(".//pm:Journal/pm:Title", ns) or article.find(".//Journal/Title")
                author_els = article.findall(".//pm:Author", ns) or article.findall(".//Author")

                pmid = pmid_el.text if pmid_el is not None else ""
                title = title_el.text if title_el is not None else "No title"
                abstract = abstract_el.text.strip() if abstract_el is not None and abstract_el.text else "Abstract not available."
                year = int(year_el.text) if year_el is not None and year_el.text else None
                venue = journal_el.text if journal_el is not None else ""
                authors = []
                for a in author_els:
                    name = a.find("pm:LastName", ns) or a.find("LastName")
                    fore = a.find("pm:ForeName", ns) or a.find("ForeName")
                    if name is not None and name.text:
                        full = f"{name.text}"
                        if fore is not None and fore.text:
                            full = f"{fore.text} {name.text}"
                        authors.append(full)

                papers.append({
                    "paperId": pmid,
                    "title": title,
                    "abstract": abstract,
                    "year": year,
                    "venue": venue,
                    "authors": authors,
                    "doi": None,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
                    "citationCount": None,
                })
        except Exception as e:
            logger.error(f"Failed to parse PubMed XML: {e}")
        return papers

    def get_paper(self, paper_id: str) -> Optional[dict]:
        """Fetch a single paper by ID (tries SS, then PubMed)."""
        meta = self._ss_paper(paper_id)
        if meta:
            return meta
        return self._pubmed_paper(paper_id)

    def _ss_paper(self, paper_id: str) -> Optional[dict]:
        """Fetch via Semantic Scholar."""
        try:
            params = {"fields": ",".join(PAPER_FIELDS)}
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(f"{SS_BASE}/paper/{paper_id}", params=params)
            if resp.status_code == 429:
                return None
            resp.raise_for_status()
            item = resp.json()
            meta = {f: item.get(f) for f in PAPER_FIELDS}
            authors_list = item.get("authors", [])
            meta["authors"] = [a.get("name", "") for a in authors_list] if authors_list else []
            if meta.get("abstract") is None:
                meta["abstract"] = "Abstract not available."
            return meta
        except Exception as e:
            logger.debug(f"SS paper fetch failed: {e}")
        return None

    def _pubmed_paper(self, pmid: str) -> Optional[dict]:
        """Fetch via PubMed."""
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(
                    f"{PUBMED_BASE}/efetch.fcgi",
                    params={"db": "pubmed", "id": pmid, "retmode": "xml"},
                )
            resp.raise_for_status()
            papers = self._parse_pubmed_xml(resp.text, [pmid])
            return papers[0] if papers else None
        except Exception as e:
            logger.error(f"PubMed paper fetch failed: {e}")
        return None
