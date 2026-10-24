"""Tests for the slider value badge and the centered access gate."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _run_app(password=None):
    from streamlit.testing.v1 import AppTest

    if password is not None:
        os.environ["APP_PASSWORD"] = password
    else:
        os.environ.pop("APP_PASSWORD", None)
    try:
        at = AppTest.from_file(
            str(Path(__file__).parent.parent / "app.py"), default_timeout=60
        )
        return at.run()
    finally:
        os.environ.pop("APP_PASSWORD", None)


class TestSliderValueBadge:
    def test_badge_shows_default_value(self):
        at = _run_app()
        assert len(at.exception) == 0
        md = " ".join(m.value for m in at.markdown)
        assert "apple-slider-value" in md
        assert ">20<" in md  # slider default is 20


class TestAccessGate:
    def test_gate_renders_prompt_and_input(self):
        at = _run_app(password="test-password")
        assert len(at.exception) == 0
        titles = [t.value for t in at.title]
        assert any("需要访问口令" in (t or "") for t in titles)
        assert len(at.text_input) >= 1
        labels = [b.label for b in at.button]
        assert any("进入" in (b or "") for b in labels)
