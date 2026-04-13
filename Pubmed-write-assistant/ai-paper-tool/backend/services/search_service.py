"""
Search Service — paper search with OpenAlex (primary) and PubMed (fallback).
"""

import logging
import os
import re
from typing import Optional

from dotenv import load_dotenv
import httpx

logger = logging.getLogger(__name__)
load_dotenv(override=True)

DEFAULT_TIMEOUT = 15
OPENALEX_BASE = "https://api.openalex.org"
PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
SEMANTICSCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"


def _translate_to_en(text: str) -> str:
    """Translate text to English using Google Translate (free, no API key)."""
    try:
        params = {
            "client": "gtx",
            "sl": "zh-CN",
            "tl": "en",
            "dt": "t",
            "q": text,
        }
        with httpx.Client(timeout=10, verify=False) as client:
            resp = client.get(TRANSLATE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data and data[0]:
            return "".join(item[0] for item in data[0] if item[0])
        return text
    except Exception as e:
        logger.debug(f"Translation failed: {e}")
        return text


def _reconstruct_abstract(inverted_index: dict) -> str:
    """Reconstruct text from OpenAlex abstract_inverted_index."""
    if not inverted_index:
        return "Abstract not available."
    words = sorted(inverted_index.items(), key=lambda x: x[1][0])
    return " ".join(w for w, _ in words)


class SearchService:
    """Searches papers using OpenAlex (primary) with PubMed fallback."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self._timeout = timeout

    def search(
        self,
        query: str,
        top_k: int = 20,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        author: Optional[str] = None,
        venue: Optional[str] = None,
    ) -> list[dict]:
        """
        Search for papers with optional filters.
        Tries OpenAlex first, then Semantic Scholar, then PubMed on error.
        """
        papers = self._openalex_search(query, top_k, year_from, year_to, author, venue)
        if len(papers) >= top_k:
            return papers[:top_k]
        logger.info(f"OpenAlex returned {len(papers)} papers, trying Semantic Scholar for: {query}")
        ss_papers = self._semantic_scholar_search(query, top_k, year_from, year_to, author, venue)
        papers.extend(ss_papers)
        if len(papers) >= top_k:
            return papers[:top_k]
        logger.warning(f"Combined results ({len(papers)}) < {top_k}, falling back to PubMed for: {query}")
        pubmed_papers = self._pubmed_search(query, top_k, year_from, year_to, author, venue)
        papers.extend(pubmed_papers)
        return papers[:top_k]

    def _openalex_search(
        self,
        query: str,
        top_k: int,
        year_from: Optional[int],
        year_to: Optional[int],
        author: Optional[str],
        venue: Optional[str],
    ) -> list[dict]:
        """Search via OpenAlex API."""
        en_query = _translate_to_en(query)
        if en_query != query:
            logger.info(f"Translated query: {query!r} → {en_query!r}")

        params = {
            "search": en_query,
            "per-page": min(top_k, 100),
            "select": "id,doi,title,authorships,publication_year,abstract_inverted_index,"
                      "primary_location,open_access",
        }

        filters = []
        if year_from and year_to:
            filters.append(f"publication_year:{year_from}-{year_to}")
        elif year_from:
            filters.append(f"publication_year:>{year_from - 1}")
        elif year_to:
            filters.append(f"publication_year:<{year_to + 1}")
        if filters:
            params["filter"] = ",".join(filters)

        try:
            with httpx.Client(timeout=self._timeout, verify=False) as client:
                resp = client.get(f"{OPENALEX_BASE}/works", params=params)

            if resp.status_code == 429:
                logger.warning("OpenAlex rate limit (429)")
                return []
            resp.raise_for_status()
            data = resp.json()

            papers = []
            for item in data.get("results", []):
                # Authors
                authors = [
                    a.get("author", {}).get("display_name", "")
                    for a in item.get("authorships", [])
                ][:10]

                # Venue
                loc = item.get("primary_location") or item.get("location") or {}
                source = loc.get("source") or {}
                venue_name = source.get("display_name", "") or ""

                # Abstract
                abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))

                # URL: try openalex URL first, then DOI
                paper_url = item.get("id", "")
                doi = item.get("doi", "")
                if not paper_url and doi:
                    paper_url = doi

                papers.append({
                    "paperId": item.get("id", ""),
                    "title": item.get("title", "No title"),
                    "abstract": abstract,
                    "year": item.get("publication_year"),
                    "venue": venue_name,
                    "authors": authors,
                    "citationCount": None,
                    "doi": doi.replace("https://doi.org/", "") if doi else None,
                    "url": paper_url,
                })

            logger.info(f"OpenAlex returned {len(papers)} papers for: {query}")
            return papers

        except Exception as e:
            logger.error(f"OpenAlex search failed: {type(e).__name__}: {e}")
            return []

    def _semantic_scholar_search(
        self,
        query: str,
        top_k: int,
        year_from: Optional[int],
        year_to: Optional[int],
        author: Optional[str],
        venue: Optional[str],
    ) -> list[dict]:
        """Search via Semantic Scholar API."""
        en_query = _translate_to_en(query)
        if en_query != query:
            logger.info(f"Translated query: {query!r} → {en_query!r}")

        ss_parts = [en_query]
        if author:
            ss_parts.append(f"author:{author}")
        if venue:
            ss_parts.append(f"venue:{venue}")
        ss_query = " ".join(ss_parts)

        year_filter = None
        if year_from and year_to:
            year_filter = f"{year_from}-{year_to}"
        elif year_from:
            year_filter = f"{year_from}-"
        elif year_to:
            year_filter = f"-{year_to}"

        params = {
            "query": ss_query,
            "limit": min(top_k, 100),
            "fields": "paperId,title,abstract,year,authors,venue,citationCount,externalIds,url",
        }
        if year_filter:
            params["year"] = year_filter

        try:
            with httpx.Client(timeout=self._timeout, verify=False) as client:
                resp = client.get(
                    f"{SEMANTICSCHOLAR_BASE}/paper/search",
                    params=params,
                )

            if resp.status_code == 429:
                logger.warning("Semantic Scholar rate limit (429)")
                return []
            resp.raise_for_status()
            data = resp.json()

            papers = []
            for item in data.get("data", []):
                authors = [
                    a.get("name", "")
                    for a in item.get("authors", [])
                ][:10]

                external_ids = item.get("externalIds", {}) or {}
                doi = external_ids.get("DOI", "")

                papers.append({
                    "paperId": item.get("paperId", ""),
                    "title": item.get("title", "No title"),
                    "abstract": item.get("abstract") or "Abstract not available.",
                    "year": item.get("year"),
                    "venue": item.get("venue", ""),
                    "authors": authors,
                    "citationCount": item.get("citationCount"),
                    "doi": doi.replace("https://doi.org/", "") if doi else None,
                    "url": item.get("url") or f"https://www.semanticscholar.org/paper/{item.get('paperId', '')}",
                })

            logger.info(f"Semantic Scholar returned {len(papers)} papers for: {query}")
            return papers

        except Exception as e:
            logger.error(f"Semantic Scholar search failed: {type(e).__name__}: {e}")
            return []

    def _pubmed_search(
        self,
        query: str,
        top_k: int,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        author: Optional[str] = None,
        venue: Optional[str] = None,
    ) -> list[dict]:
        """Search via PubMed E-utilities as fallback with optional filters."""
        en_query = _translate_to_en(query)
        if en_query != query:
            logger.info(f"Translated query: {query!r} → {en_query!r}")

        pubmed_parts = [en_query]
        if author:
            pubmed_parts.append(f"{author}[Author]")
        if venue:
            pubmed_parts.append(f"{venue}[Journal]")
        pubmed_query = " AND ".join(pubmed_parts)

        year_filter = ""
        if year_from and year_to:
            year_filter = f" ({year_from}:{year_to}[Date - Publication])"
        elif year_from:
            year_filter = f" ({year_from}[Date - Publication])"
        elif year_to:
            year_filter = f" ({year_to}[Date - Publication])"

        full_query = pubmed_query + year_filter

        try:
            with httpx.Client(timeout=self._timeout, verify=False) as client:
                search_resp = client.get(
                    f"{PUBMED_BASE}/esearch.fcgi",
                    params={"db": "pubmed", "term": full_query, "retmax": top_k, "retmode": "json"},
                )
            search_resp.raise_for_status()
            search_data = search_resp.json()
            ids = search_data.get("esearchresult", {}).get("idlist", [])
            if not ids:
                logger.info(f"PubMed returned 0 papers for: {query}")
                return []

            id_str = ",".join(ids)
            with httpx.Client(timeout=self._timeout, verify=False) as client:
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
                        full = name.text
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
        """Fetch a single paper by OpenAlex ID or PubMed PMID."""
        if paper_id.startswith("https://openalex.org/"):
            return self._openalex_paper(paper_id)
        return self._pubmed_paper(paper_id)

    def _openalex_paper(self, paper_id: str) -> Optional[dict]:
        """Fetch via OpenAlex by work ID."""
        try:
            work_url = f"{OPENALEX_BASE}/works/{paper_id.split('/')[-1]}"
            with httpx.Client(timeout=self._timeout, verify=False) as client:
                resp = client.get(
                    work_url,
                    params={"select": "id,doi,title,authorships,publication_year,"
                                     "abstract_inverted_index,primary_location,open_access"}
                )
            if resp.status_code == 429:
                return None
            resp.raise_for_status()
            item = resp.json()

            authors = [
                a.get("author", {}).get("display_name", "")
                for a in item.get("authorships", [])
            ]
            loc = item.get("primary_location") or {}
            source = loc.get("source") or {}
            venue_name = source.get("display_name", "")
            abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))
            doi = item.get("doi", "")

            return {
                "paperId": item.get("id", ""),
                "title": item.get("title", "No title"),
                "abstract": abstract,
                "year": item.get("publication_year"),
                "venue": venue_name,
                "authors": authors,
                "citationCount": None,
                "doi": doi.replace("https://doi.org/", "") if doi else None,
                "url": item.get("id", "") or doi,
            }
        except Exception as e:
            logger.debug(f"OpenAlex paper fetch failed: {e}")
        return None

    def _pubmed_paper(self, pmid: str) -> Optional[dict]:
        """Fetch via PubMed."""
        try:
            with httpx.Client(timeout=self._timeout, verify=False) as client:
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
