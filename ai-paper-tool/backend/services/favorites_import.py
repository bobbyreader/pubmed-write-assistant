"""
Favorites Import — convert a PubMed research-assistant favorites backup
(pubmed-assistant-v2 "favorites-backup" JSON) into paper dicts usable as
seed literature for the writing pipeline.

Backup format:
    {"app": "pubmed-assistant-v2", "kind": "favorites-backup", "version": 1,
     "exportedAt": ..., "count": N,
     "favorites": [{"pmid", "title", "authors": [...], "journal", "year",
                    "doi", "pmc", "pubtype", "tags", "note", ...}]}

A bare list of favorite objects is also accepted. Favorites carry no
abstract text, so `enrich_abstracts` optionally fills abstracts in from
PubMed (NCBI E-utilities efetch, one batch call). Enrichment is
best-effort: any failure leaves abstracts empty and never raises.
"""

import logging
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _to_year(value) -> int | None:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else None


def parse_favorites_backup(data) -> list[dict]:
    """
    Parse a favorites backup payload into SearchService-shaped paper dicts.
    Raises ValueError with a user-readable message on unusable input.
    """
    if isinstance(data, dict):
        favorites = data.get("favorites")
        if not isinstance(favorites, list):
            raise ValueError("文件格式不对：没有找到 favorites 列表（请使用研究助手的「导出备份 (JSON)」文件）")
    elif isinstance(data, list):
        favorites = data
    else:
        raise ValueError("文件格式不对：顶层应为 JSON 对象或数组")

    papers: list[dict] = []
    seen: set[str] = set()
    for fav in favorites:
        if not isinstance(fav, dict):
            continue
        pmid = str(fav.get("pmid") or "").strip()
        title = str(fav.get("title") or "").strip()
        if not pmid or not title or pmid in seen:
            continue
        seen.add(pmid)
        papers.append({
            "paperId": pmid,
            "pmid": pmid,
            "title": title,
            "abstract": str(fav.get("abstract") or ""),
            "year": _to_year(fav.get("year")),
            "venue": fav.get("journal") or fav.get("venue") or "",
            "authors": [a for a in (fav.get("authors") or []) if a],
            "citationCount": None,
            "doi": fav.get("doi") or None,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "pmc": fav.get("pmc") or "",
            "tags": fav.get("tags") or [],
            "note": fav.get("note") or "",
        })

    if not papers:
        raise ValueError("收藏文件里没有可用的文献（每条需要 PMID 与标题）")
    return papers


def _parse_pubmed_abstracts(xml_text: str) -> dict[str, str]:
    """Map PMID -> abstract text from an efetch XML response."""
    abstracts: dict[str, str] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning(f"efetch XML parse failed: {e}")
        return abstracts
    for article in root.iter("PubmedArticle"):
        pmid_el = article.find(".//MedlineCitation/PMID")
        if pmid_el is None or not pmid_el.text:
            continue
        parts = []
        for node in article.iter("AbstractText"):
            text = "".join(node.itertext()).strip()
            if not text:
                continue
            label = node.get("Label")
            parts.append(f"{label}: {text}" if label else text)
        if parts:
            abstracts[pmid_el.text.strip()] = " ".join(parts)
    return abstracts


def enrich_abstracts(papers: list[dict], timeout: int = 20) -> list[dict]:
    """
    Fill missing abstracts from PubMed efetch (single batch call).
    Best-effort: network/parse failures leave papers unchanged.
    """
    missing = [p for p in papers if not p.get("abstract") and p.get("pmid")]
    if not missing:
        return papers
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                EFETCH_URL,
                params={"db": "pubmed",
                        "id": ",".join(p["pmid"] for p in missing),
                        "retmode": "xml"},
            )
        resp.raise_for_status()
        abstracts = _parse_pubmed_abstracts(resp.text)
        filled = 0
        for paper in missing:
            abstract = abstracts.get(paper["pmid"])
            if abstract:
                paper["abstract"] = abstract
                filled += 1
        logger.info(f"Enriched abstracts for {filled}/{len(missing)} seed papers")
    except Exception as e:
        logger.warning(f"Abstract enrichment failed (continuing without): {e}")
    return papers
