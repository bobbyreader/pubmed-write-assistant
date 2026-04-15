"""Tests for ExportService — verifies Word/PDF/MD export with Chinese font."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.export_service import (
    export_word,
    export_pdf,
    _md_to_plain_text,
    _parse_md_tables,
    _split_sections,
)


class TestMdToPlainText:
    def test_strips_code_blocks(self):
        assert _md_to_plain_text("```json\n{\"key\": 1}\n```") == '{"key": 1}'
        assert _md_to_plain_text("```\nsome code\n```") == "some code"

    def test_strips_images(self):
        assert _md_to_plain_text("![alt](url)") == ""
        assert _md_to_plain_text("Text ![alt](url) more") == "Text  more"

    def test_converts_links_to_text(self):
        assert _md_to_plain_text("[click here](https://example.com)") == "click here"

    def test_strips_bold_italic(self):
        assert _md_to_plain_text("**bold** and *italic*") == "bold and italic"

    def test_strips_headings(self):
        assert _md_to_plain_text("# Title\n## Section") == "Title\nSection"

    def test_converts_lists(self):
        result = _md_to_plain_text("- item\n* another\n+ third")
        # Bullet markers are converted to • character
        assert "• item" in result
        assert "• another" in result
        assert "• third" in result
        result2 = _md_to_plain_text("1. numbered item")
        # Numbered lists are converted to plain numbers with spacing
        assert "numbered" in result2

    def test_strips_extra_newlines(self):
        result = _md_to_plain_text("para1\n\n\n\n\npara2")
        assert "\n\n\n" not in result


class TestParseMdTables:
    def test_parses_simple_table(self):
        md = "| Header1 | Header2 |\n|----------|----------|\n| Cell1   | Cell2   |"
        tables = _parse_md_tables(md)
        assert len(tables) == 1
        rows, num_cols = tables[0]
        assert num_cols == 2
        assert rows[0] == ["Header1", "Header2"]
        assert rows[1] == ["Cell1", "Cell2"]

    def test_parses_multiple_tables(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n\n| C | D |\n|---|---|\n| 3 | 4 |"
        tables = _parse_md_tables(md)
        assert len(tables) == 2

    def test_parses_table_with_markdown_in_cells(self):
        md = "| **Bold** | *Italic* |\n|---|---|\n| [link](url) | plain |"
        tables = _parse_md_tables(md)
        rows, _ = tables[0]
        # Markdown is preserved in cells (render functions strip it)
        assert rows[0] == ["**Bold**", "*Italic*"]

    def test_no_tables_returns_empty(self):
        assert _parse_md_tables("No tables here") == []


class TestSplitSections:
    def test_splits_on_headings(self):
        md = "# Title\n\nBody content.\n\n## Section1\n\nSection body."
        sections = _split_sections(md)
        headings = [h for h, _ in sections]
        assert "Title" in headings
        assert "Section1" in headings

    def test_handles_content_before_first_heading(self):
        md = "Intro text without heading.\n\n## Section"
        sections = _split_sections(md)
        # First section may have empty heading
        bodies = [b.strip() for _, b in sections if b.strip()]
        assert "Intro text without heading." in bodies[0]


class TestExportWord:
    def test_export_word_produces_bytes(self):
        md = "# Test Paper\n\n## Abstract\n\nThis is a test abstract.\n\n## Introduction\n\nIntroduction text."
        result = export_word(md, title="Test Paper")
        assert isinstance(result, bytes)
        assert len(result) > 0
        # DOCX is a ZIP file — starts with PK
        assert result[:2] == b"PK"

    def test_export_word_with_table(self):
        md = "# Paper\n\n## Methods\n\n| Step | Action |\n|------|--------|\n| 1    | Setup  |\n| 2    | Run    |"
        result = export_word(md, title="Table Paper")
        assert isinstance(result, bytes)
        assert result[:2] == b"PK"

    def test_export_word_minimal_content(self):
        md = "# Short\n\nJust a title and one paragraph."
        result = export_word(md)
        assert isinstance(result, bytes)
        assert len(result) > 0


class TestExportPDF:
    def test_export_pdf_produces_bytes(self):
        md = "# Test Paper\n\n## Abstract\n\nThis is a test abstract."
        result = export_pdf(md, title="Test Paper")
        assert isinstance(result, bytes)
        assert len(result) > 0
        # PDF starts with %PDF
        assert result[:4] == b"%PDF"

    def test_export_pdf_with_table(self):
        md = "# Paper\n\n## Methods\n\n| Step | Action |\n|------|--------|\n| 1    | Setup  |"
        result = export_pdf(md, title="Table Paper")
        assert isinstance(result, bytes)
        assert result[:4] == b"%PDF"

    def test_export_pdf_with_chinese_content(self):
        md = "# 测试论文\n\n## 摘要\n\n这是一段中文摘要内容。"
        result = export_pdf(md, title="测试论文")
        assert isinstance(result, bytes)
        assert result[:4] == b"%PDF"

    def test_export_pdf_empty_content(self):
        md = "# Empty\n\n"
        result = export_pdf(md)
        assert isinstance(result, bytes)
        assert result[:4] == b"%PDF"
