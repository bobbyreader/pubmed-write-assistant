"""
RAG Service — prepares context from citation_map for agents.
Implements full-context injection strategy.
"""

import logging
from typing import Optional

from backend.services.citation_service import CitationService

logger = logging.getLogger(__name__)


class RAGService:
    """
    RAG context preparation for agent prompts.
    Strategy: Full-context injection (all abstracts passed to Writer).
    """

    def __init__(self, citation_service: CitationService):
        self.citation_service = citation_service

    def build_researcher_context(self, topic: str) -> str:
        """
        Build search context for the Researcher agent.
        (Researcher uses direct API search, minimal prompt context needed.)
        """
        return f"Topic: {topic}\n\nSearch for up to 10 highly relevant papers. Prioritize recent and highly-cited papers."

    def build_writer_context(self) -> str:
        """
        Build full RAG context for the Writer agent.
        Injects all paper abstracts (full-context strategy).
        """
        citation_map = self.citation_service.get_all()
        if not citation_map:
            return "No papers found. Citation map is empty."

        parts = []
        for cite_id, meta in sorted(citation_map.items()):
            title = meta.get("title", "Unknown Title")
            year = meta.get("year", "Unknown")
            authors = meta.get("authors", [])
            if isinstance(authors, list) and authors:
                authors_str = ", ".join(authors[:3])
                if len(authors) > 3:
                    authors_str += " et al."
            else:
                authors_str = "Unknown"
            abstract = meta.get("abstract", "No abstract available.")
            parts.append(
                f"--- {cite_id} ---\n"
                f"Title: {title}\n"
                f"Authors: {authors_str} ({year})\n"
                f"Abstract: {abstract}\n"
            )
        return "\n\n".join(parts)

    def build_reviewer_context(self) -> str:
        """
        Build context for the Reviewer agent.
        Includes citation_map overview + abstracts.
        """
        return self.build_writer_context()

    def build_editor_context(self) -> str:
        """
        Build context for the Editor agent.
        Same as reviewer context.
        """
        return self.build_writer_context()
