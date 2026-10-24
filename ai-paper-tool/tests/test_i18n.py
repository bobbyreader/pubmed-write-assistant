"""Tests for the zh/en UI internationalization layer."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _placeholders(text: str) -> set:
    return set(re.findall(r"\{(\w+)\}", text))


class TestStringTables:
    def test_zh_en_key_and_placeholder_parity(self):
        from utils.i18n import STRINGS, PROGRESS

        for table_name, table in [("STRINGS", STRINGS), ("PROGRESS", PROGRESS)]:
            for key, entry in table.items():
                assert set(entry.keys()) == {"zh", "en"}, f"{table_name}.{key}"
                assert _placeholders(entry["zh"]) == _placeholders(entry["en"]), \
                    f"{table_name}.{key} placeholder mismatch"
                assert entry["zh"].strip() and entry["en"].strip(), \
                    f"{table_name}.{key} empty"

    def test_pm_formats_both_languages(self):
        from utils.i18n import pm

        assert pm("prog_seeds", "zh", n=3) == "正在使用导入的 3 篇种子文献…"
        assert pm("prog_seeds", "en", n=3) == "Using 3 imported seed papers..."
        assert pm("err_no_papers", "zh") != pm("err_no_papers", "en")
        assert pm("missing_key", "zh") == "missing_key"


class TestAppRendersBothLanguages:
    def _run_app(self, lang=None):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file(
            str(Path(__file__).parent.parent / "app.py"), default_timeout=60
        )
        if lang:
            at.session_state["lang"] = lang
        return at.run()

    def test_default_language_is_chinese(self):
        at = self._run_app()
        assert len(at.exception) == 0
        md = " ".join(m.value for m in at.markdown)
        assert "PubMed 论文写作助手" in md
        assert "研究主题" in md
        buttons = [b.label for b in at.button]
        assert any("生成论文" in (b or "") for b in buttons)
        # Language toggle present and set to zh
        assert at.segmented_control[0].value == "zh"

    def test_english_render(self):
        at = self._run_app(lang="en")
        assert len(at.exception) == 0
        md = " ".join(m.value for m in at.markdown)
        assert "PubMed Paper Assistant" in md
        assert "Research Topic" in md
        buttons = [b.label for b in at.button]
        assert any("Generate Paper" in (b or "") for b in buttons)
        assert at.segmented_control[0].value == "en"
