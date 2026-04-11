"""
Citation Service — manages citation_map lifecycle.
Builds, validates, and formats citation maps.
"""

import logging
from typing import Optional

from backend.services.search_service import SearchService

logger = logging.getLogger(__name__)


class CitationService:
    """
    Manages the global citation_map used by all agents.
    citation_map: { "[1]": { title, paperId, doi, year, authors, abstract, url, venue, citationCount } }
    """

    def __init__(self, search_service: SearchService):
        self.search_service = search_service
        self.citation_map: dict[str, dict] = {}

    def build_from_search(self, topic: str, top_k: int = 10) -> dict[str, dict]:
        """
        Search papers and build citation_map.
        Returns the citation_map.
        """
        papers = self.search_service.search(topic, top_k=top_k)
        self.citation_map = {}
        for i, paper in enumerate(papers, start=1):
            key = f"[{i}]"
            self.citation_map[key] = {
                "title": paper.get("title", "Unknown Title"),
                "paperId": paper.get("paperId", ""),
                "doi": paper.get("doi"),
                "year": paper.get("year"),
                "authors": paper.get("authors", []),
                "abstract": paper.get("abstract", ""),
                "url": paper.get("url", ""),
                "venue": paper.get("venue"),
                "citationCount": paper.get("citationCount", 0),
            }
        logger.info(f"Built citation_map with {len(self.citation_map)} papers")
        return self.citation_map

    def get(self, cite_id: str) -> Optional[dict]:
        """Get paper metadata by citation ID (e.g., '[1]')."""
        return self.citation_map.get(cite_id)

    def get_all(self) -> dict[str, dict]:
        """Return the full citation_map."""
        return self.citation_map

    def format_for_references(self) -> str:
        """
        Format citation_map as a References section string.
        Format: [N] Authors. Title. Venue, Year. DOI: ...
        """
        lines = []
        for cite_id, meta in sorted(self.citation_map.items()):
            authors = meta.get("authors", [])
            if isinstance(authors, list) and authors:
                authors_str = ", ".join(authors[:3])
                if len(authors) > 3:
                    authors_str += ", et al."
            else:
                authors_str = "Unknown Authors"

            title = meta.get("title", "Unknown Title")
            year = meta.get("year", "n.d.")
            venue = meta.get("venue") or "Preprint"
            doi = meta.get("doi")

            line = f"{cite_id} {authors_str}. {title}. {venue}, {year}."
            if doi:
                line += f" DOI: {doi}"
            lines.append(line)
        return "\n".join(lines)

    def validate_citations(self, text: str) -> list[str]:
        """
        Check if all [N] citations in text exist in citation_map.
        Returns list of invalid/unknown citation IDs found.
        """
        import re
        cited = re.findall(r"\[(\d+)\]", text)
        invalid = []
        for num in cited:
            key = f"[{num}]"
            if key not in self.citation_map:
                invalid.append(key)
        return invalid

    def abstracts_context(self) -> str:
        """Concatenate all abstracts for RAG context injection."""
        parts = []
        for cite_id, meta in sorted(self.citation_map.items()):
            title = meta.get("title", "Unknown")
            abstract = meta.get("abstract", "No abstract available.")
            parts.append(f"{cite_id}: {title}\n: {abstract}")
        return "\n\n".join(parts)
