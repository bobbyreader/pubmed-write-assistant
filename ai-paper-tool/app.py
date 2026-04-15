"""
Streamlit Frontend for AI Paper Tool.
Provides interactive paper generation with multi-round review visibility.
"""
import os
import logging
import threading
import queue
import time
from datetime import datetime
from typing import Optional

import streamlit as st

from workflows.writing_pipeline import WritingPipeline
from utils.export_service import export_word, export_pdf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="PubMed Paper Assistant",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── External Resources ──────────────────────────────
# Font Awesome 6 + Google Fonts via HTML injection
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" integrity="sha512-DTOQO9RWCH3ppGqcWaEA1BIZOC6xxalwEsw9c2QQeAIftl+Vegovlnee1c9QX4TctnWMn13TZye+giMm8e2LwA==" crossorigin="anonymous" referrerpolicy="no-referrer" />
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,400&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# Custom CSS
with open(os.path.join(os.path.dirname(__file__), ".streamlit", "style.css")) as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# ─── Session State ─────────────────────────────────
def _init_state():
    defaults = {
        "citation_map": {},
        "topic": "",
        "pipeline_result": None,
        "rounds": [],
        "started": False,
        "error": "",
        "generating": False,
        "generating_done": False,
        "pipeline_progress_phase": "",
        "pipeline_progress_msg": "",
        "pipeline_progress_fraction": 0.0,
        "progress_queue": None,
        "debug_api_result": None,
        "debug_search_result": None,
        "debug_api_loading": False,
        "debug_search_loading": False,
        "dry_running": False,
        "dry_topic": "",
        "dry_result": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()


# ─── Helpers ──────────────────────────────────────
def load_env():
    from dotenv import load_dotenv
    load_dotenv(override=True)
    return {
        "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "base_url": os.getenv("ANTHROPIC_BASE_URL", "https://api.minimax.chat/v1"),
        "model": os.getenv("ANTHROPIC_MODEL", "MiniMax-M2.7-highspeed"),
        "ss_api_key": os.getenv("SEMANTICSCHOLAR_API_KEY", ""),
    }


def save_env(api_key: str, base_url: str, model: str, ss_api_key: str = "") -> tuple[bool, str]:
    try:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        with open(env_path, "w") as f:
            f.write(f"ANTHROPIC_API_KEY={api_key}\n")
            f.write(f"ANTHROPIC_BASE_URL={base_url}\n")
            f.write(f"ANTHROPIC_MODEL={model}\n")
            if ss_api_key.strip():
                f.write(f"SEMANTICSCHOLAR_API_KEY={ss_api_key.strip()}\n")
        os.environ["ANTHROPIC_API_KEY"] = api_key
        os.environ["ANTHROPIC_BASE_URL"] = base_url
        os.environ["ANTHROPIC_MODEL"] = model
        os.environ["SEMANTICSCHOLAR_API_KEY"] = ss_api_key.strip()
        return True, "Saved to .env"
    except Exception as e:
        return False, str(e)


# ─── Render: Paper Card (sidebar) ─────────────────
def render_paper_card(cite_id: str, meta: dict):
    title = meta.get("title", "Unknown Title")
    year = meta.get("year", "n.d.")
    authors = meta.get("authors", [])
    if isinstance(authors, list) and authors:
        authors_str = ", ".join(authors[:2])
        if len(authors) > 2:
            authors_str += " + others"
    else:
        authors_str = "Unknown"
    venue = meta.get("venue") or ""
    abstract = meta.get("abstract", "")
    abstract_short = (abstract[:180] + "…") if len(abstract) > 180 else abstract
    if abstract_short == "Abstract not available.":
        abstract_short = ""

    url = meta.get("url", "")
    label = "View on PubMed" if "pubmed" in url else "View Source"

    st.markdown(f"""
    <div class="paper-card">
      <div class="paper-card-title">{cite_id} {title[:70]}{'…' if len(title) > 70 else ''}</div>
      <div class="paper-card-meta">{authors_str} &middot; {year}{' &middot; ' + venue if venue else ''}</div>
      {f'<div class="paper-card-abstract">{abstract_short}</div>' if abstract_short else ''}
      {f'<a class="paper-card-link" href="{url}" target="_blank"><i class="fa-solid fa-arrow-up-right-from-square"></i> {label}</a>' if url else ''}
    </div>
    """, unsafe_allow_html=True)


# ─── Render: Round Card ───────────────────────────
def render_round_card(record):
    phase_labels = {
        "search": "Literature Search",
        "write": "Draft Generation",
        "review": "Peer Review",
        "edit": "Editorial Revision",
    }
    phase_icons = {
        "search": "fa-magnifying-glass",
        "write": "fa-pen-nib",
        "review": "fa-eye",
        "edit": "fa-pen",
    }
    icon = phase_icons.get(record.phase, "fa-circle")
    label = phase_labels.get(record.phase, record.phase.capitalize())

    st.markdown(f"""
    <div class="round-card">
      <div class="round-phase-label">
        <i class="fa-solid {icon}"></i>&nbsp; Round {record.round_num} &mdash; {label}
      </div>
    """, unsafe_allow_html=True)

    if record.phase == "search":
        st.markdown(f'<div class="progress-text"><i class="fa-solid fa-check" style="color:var(--color-success)"></i>&nbsp; {record.notes}</div>')

    elif record.phase == "write":
        if record.draft_content:
            st.markdown("#### Generated Draft")
            st.markdown(record.draft_content)

    elif record.phase == "review":
        if record.review_content:
            rc = record.review_content
            score = rc.get("score", 0)
            cite_acc = rc.get("citation_accuracy_score", 10)
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Overall Score", f"{score}/10")
            with col2:
                st.metric("Citation Accuracy", f"{cite_acc}/10")
            st.progress(score / 10, text=f"Quality score: {score}/10")

            if rc.get("hallucination_flags"):
                st.error(f"**Hallucination detected:** {', '.join(rc['hallucination_flags'])}")

            if rc.get("strengths"):
                with st.expander("Strengths"):
                    for s in rc["strengths"]:
                        st.write(f"&nbsp;&nbsp;&nbsp;{s}")
            if rc.get("weaknesses"):
                with st.expander("Areas for Improvement"):
                    for w in rc["weaknesses"]:
                        st.write(f"&nbsp;&nbsp;&nbsp;{w}")
            if rc.get("suggestions"):
                with st.expander("Suggestions"):
                    for sg in rc["suggestions"]:
                        st.write(f"**{sg.get('section', '')}** — {sg.get('suggestion', '')}")
            if rc.get("summary"):
                st.markdown(f"**Reviewer's Summary:** {rc['summary']}")
        if record.error:
            st.error(f"Error: {record.error}")

    elif record.phase == "edit":
        if record.edit_content:
            ec = record.edit_content
            changes = ec.get("changes_made", [])
            if changes:
                st.success(f"Changes applied: {', '.join(changes)}")
            else:
                st.success("No further changes needed")
            if ec.get("revised_draft"):
                with st.expander("Revised Draft"):
                    st.markdown(ec["revised_draft"])
            unresolved = ec.get("unresolved_issues", [])
            if unresolved:
                st.warning(f"Unresolved: {', '.join(unresolved)}")
        if record.error:
            st.error(f"Error: {record.error}")

    st.markdown("</div>")  # close round-card


# ─── Page: Main ────────────────────────────────────
def page_main():
    st.markdown('<div class="page-hero">', unsafe_allow_html=True)
    st.markdown('<h1 class="page-hero-title">PubMed Paper Assistant</h1>', unsafe_allow_html=True)
    st.markdown('<p class="page-hero-sub">Generate publication-ready research papers with verified citations</p>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ─── Sidebar ─────────────────────────────────────
    with st.sidebar:
        st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-section-title">Retrieved Papers</div>', unsafe_allow_html=True)
        citation_map = st.session_state.citation_map
        if citation_map:
            for cite_id, meta in sorted(citation_map.items()):
                render_paper_card(cite_id, meta)
        else:
            st.markdown('<div class="empty-state"><i class="fa-regular fa-folder-open" style="font-size:1.5rem;margin-bottom:0.5rem;display:block;color:var(--color-text-muted)"></i>Search to retrieve papers</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<hr>', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-section">', unsafe_allow_html=True)
        st.markdown('<div class="sidebar-section-title">Configuration</div>', unsafe_allow_html=True)
        env = load_env()
        st.markdown(f'<div class="paper-card-meta">Model: <strong>{env["model"]}</strong></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="paper-card-meta" style="word-break:break-all">Endpoint: {env["base_url"]}</div>', unsafe_allow_html=True)
        is_cloud = bool(os.getenv("ANTHROPIC_API_KEY", ""))
        if is_cloud:
            st.markdown('<div class="paper-card-meta" style="color:var(--color-success)"><i class="fa-solid fa-lock"></i>&nbsp; API key via environment</div>', unsafe_allow_html=True)
        else:
            key = env["api_key"]
            masked = (key[:4] + "****" + key[-4:]) if len(key) > 8 else "****"
            st.markdown(f'<div class="paper-card-meta">API Key: {masked}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<hr>', unsafe_allow_html=True)
        if st.button("Reset Session", icon="fa-arrows-rotate"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # ─── Hero Search Section ────────────────────────
    st.markdown('<div class="hero-search-wrapper">', unsafe_allow_html=True)

    topic = st.text_input(
        "",
        placeholder="Search research topic — e.g. LLM reasoning in scientific discovery, 大语言模型在医学影像中的应用",
        label_visibility="collapsed",
        key="hero_topic_input",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # ─── Filters ───────────────────────────────────
    st.markdown('<div class="filters-row">', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1:
        search_top_k = st.slider("Papers", min_value=5, max_value=50, value=20, step=5)
    with col2:
        year_from = st.number_input("From", min_value=1990, max_value=2026, value=2018)
    with col3:
        year_to = st.number_input("To", min_value=1990, max_value=2026, value=2026)
    with col4:
        author = st.text_input("Author", placeholder="Any author", label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

    col_f5, _ = st.columns([1, 3])
    with col_f5:
        venue = st.text_input("Journal / Venue", placeholder="Any journal", label_visibility="collapsed")

    st.markdown("")

    col_gen, _, _ = st.columns([1, 1, 1])
    with col_gen:
        disabled = st.session_state.generating or not topic.strip()
        st.markdown(f"""
        <button class="btn-generate"{" disabled" if disabled else ""}>
          <i class="fa-solid fa-wand-magic-sparkles"></i>
          &nbsp;Generate Paper
        </button>
        """, unsafe_allow_html=True)
        generate_btn = st.button(
            "",
            disabled=disabled,
            label_visibility="hidden",
        )

    if generate_btn and topic.strip():
        st.session_state.generating = True
        st.session_state.generating_done = False
        st.session_state.started = True
        st.session_state.topic = topic.strip()
        st.session_state.error = ""
        st.session_state.rounds = []
        st.session_state.pipeline_result = None
        st.session_state.citation_map = {}
        st.session_state.pipeline_progress_phase = "init"
        st.session_state.pipeline_progress_msg = "Starting pipeline…"
        st.session_state.pipeline_progress_fraction = 0.0

        q: queue.Queue = queue.Queue()
        st.session_state.progress_queue = q

        def _run_pipeline(
            q_out: queue.Queue,
            topic_in: str,
            top_k: int,
            yf: Optional[int],
            yt: Optional[int],
            auth: Optional[str],
            ven: Optional[str],
        ):
            try:
                pl = WritingPipeline()
                pl.set_progress_callback(
                    lambda phase, msg, frac: q_out.put(("progress", phase, msg, frac))
                )
                result = pl.run(
                    topic_in,
                    search_top_k=top_k,
                    year_from=yf if yf else None,
                    year_to=yt if yt else None,
                    author=(auth or "").strip() or None,
                    venue=(ven or "").strip() or None,
                )
                q_out.put(("result", result))
            except Exception as e:
                logger.exception("Pipeline thread failed")
                q_out.put(("error", str(e)))

        t = threading.Thread(
            target=_run_pipeline,
            args=(
                q,
                topic.strip(),
                search_top_k,
                year_from,
                year_to,
                author if (author or "").strip() else None,
                venue if (venue or "").strip() else None,
            ),
            daemon=True,
        )
        t.start()
        st.rerun()

    # ─── Poll progress ─────────────────────────────
    if st.session_state.generating and not st.session_state.generating_done:
        q = st.session_state.progress_queue
        if q is not None:
            while True:
                try:
                    item = q.get_nowait()
                    if item[0] == "progress":
                        _, phase, msg, frac = item
                        st.session_state.pipeline_progress_phase = phase
                        st.session_state.pipeline_progress_msg = msg
                        st.session_state.pipeline_progress_fraction = frac
                    elif item[0] == "result":
                        st.session_state.pipeline_result = item[1]
                        st.session_state.generating_done = True
                        st.session_state.generating = False
                        if item[1].success:
                            st.session_state.citation_map = item[1].citation_map
                            st.session_state.rounds = item[1].rounds
                        else:
                            st.session_state.error = item[1].error
                        st.rerun()
                    elif item[0] == "error":
                        st.session_state.error = item[1]
                        st.session_state.generating_done = True
                        st.session_state.generating = False
                        st.rerun()
                except queue.Empty:
                    break
        time.sleep(1)
        st.rerun()

    if st.session_state.generating:
        phase = st.session_state.pipeline_progress_phase
        msg = st.session_state.pipeline_progress_msg
        frac = st.session_state.pipeline_progress_fraction
        phase_icons = {
            "init": "fa-gears",
            "research": "fa-magnifying-glass",
            "write": "fa-pen-nib",
            "review": "fa-eye",
            "edit": "fa-pen",
            "finalize": "fa-floppy-disk",
        }
        icon = phase_icons.get(phase, "fa-spinner")
        spin = " fa-spin" if phase in ("init", "research", "write") else ""
        st.markdown(f"""
        <div class="progress-wrapper">
          <div class="progress-text"><i class="fa-solid {icon}{spin}"></i>&nbsp; {msg}</div>
        </div>
        """, unsafe_allow_html=True)
        st.progress(frac if frac > 0 else None)

    if st.session_state.error:
        st.error(st.session_state.error)

    # ─── Results ───────────────────────────────────
    if st.session_state.started and st.session_state.pipeline_result:
        result = st.session_state.pipeline_result

        if result.success:
            st.success(
                f"Done — {'terminated early (high quality)' if result.early_exit else f'completed in {len(result.rounds)} rounds'}"
            )

            tab1, tab2, tab3 = st.tabs([
                "  Draft  ",
                "  References  ",
                "  Iteration History  ",
            ])

            with tab1:
                st.markdown("#### Final Paper")
                if result.final_draft:
                    st.markdown(result.final_draft)
                    md_content = result.final_draft + "\n\n---\n\n## References\n\n" + result.references
                    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

                    d1, d2, d3 = st.columns([1, 1, 1])
                    with d1:
                        st.download_button(
                            "Markdown",
                            data=md_content,
                            file_name=f"paper_{ts}.md",
                            mime="text/markdown",
                            icon="fa-file-lines",
                        )
                    with d2:
                        st.download_button(
                            "Word",
                            data=export_word(md_content, st.session_state.topic),
                            file_name=f"paper_{ts}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            icon="fa-file-word",
                        )
                    with d3:
                        st.download_button(
                            "PDF",
                            data=export_pdf(md_content, st.session_state.topic),
                            file_name=f"paper_{ts}.pdf",
                            mime="application/pdf",
                            icon="fa-file-pdf",
                        )
                else:
                    st.warning("No draft generated")

            with tab2:
                st.markdown("#### References")
                st.markdown(f'<div class="refs-content">{result.references}</div>', unsafe_allow_html=True)

            with tab3:
                st.markdown("#### Iteration Rounds")
                for record in st.session_state.rounds:
                    render_round_card(record)

    # ─── Onboarding ─────────────────────────────────
    if not st.session_state.started:
        st.markdown("""
        <div class="how-it-works">
          <h3>How it works</h3>
          <ol>
            <li><strong>Enter</strong> a research topic — Chinese or English, your choice</li>
            <li><strong>Click</strong> Generate Paper — the pipeline searches literature, writes, and reviews automatically</li>
            <li><strong>Download</strong> as Markdown, Word, or PDF — all citations are verified against source papers</li>
          </ol>
          <div style="margin-top:1rem;padding:0.75rem 1rem;background:rgba(124,111,91,0.05);border-left:3px solid var(--color-primary-light);border-radius:6px;font-size:0.85rem;color:var(--color-text-secondary);">
            <i class="fa-solid fa-shield-halved" style="color:var(--color-primary)"></i>&nbsp; Anti-hallucination: every citation is validated against the retrieved paper map.
          </div>
        </div>
        """, unsafe_allow_html=True)


# ─── Page: Settings ─────────────────────────────────
def page_settings():
    st.markdown('<div class="page-hero">', unsafe_allow_html=True)
    st.markdown('<h1 class="page-hero-title">Settings</h1>', unsafe_allow_html=True)
    st.markdown('<p class="page-hero-sub">Configure API credentials and test pipeline components</p>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    tab_api, tab_debug = st.tabs(["  API Configuration  ", "  Debug Console  "])

    with tab_api:
        st.markdown('<div class="settings-card">', unsafe_allow_html=True)
        st.markdown("<h3>API Configuration</h3>", unsafe_allow_html=True)

        env_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        env_base_url = os.getenv("ANTHROPIC_BASE_URL", "")
        env_model = os.getenv("ANTHROPIC_MODEL", "")
        env_ss_key = os.getenv("SEMANTICSCHOLAR_API_KEY", "")
        is_cloud = bool(env_api_key)

        if is_cloud:
            st.success("API key is configured via environment variables (cloud deployment). Changes must be made through platform settings.")
        else:
            st.caption("Credentials are saved to `.env` and take effect immediately. Never commit `.env` to version control.")

        env = load_env()

        with st.form("env_form", border=True):
            if is_cloud:
                st.text_input("ANTHROPIC_API_KEY", value="•" * 20, disabled=True, help="Set via environment variable")
                st.text_input("ANTHROPIC_BASE_URL", value=env_base_url, disabled=True)
                st.text_input("ANTHROPIC_MODEL", value=env_model, disabled=True)
                st.text_input("SEMANTICSCHOLAR_API_KEY (optional)", value="•" * 20 if env_ss_key else "", disabled=True)
                st.info("Environment variables are read-only. Contact your administrator to change them.")
            else:
                api_key = st.text_input("ANTHROPIC_API_KEY", value=env["api_key"], type="password", help="MiniMax API key")
                base_url = st.text_input("ANTHROPIC_BASE_URL", value=env["base_url"], help="Anthropic-compatible endpoint")
                model = st.text_input("ANTHROPIC_MODEL", value=env["model"], help="Default: MiniMax-M2.7-highspeed")
                ss_api_key = st.text_input("SEMANTICSCHOLAR_API_KEY (optional)", value=env.get("ss_api_key", ""), type="password", help="Semantic Scholar API key — increases rate limit. Free at semanticscholar.org")
                st.form_submit_button("Save to .env", icon="fa-floppy-disk")

        # Current config display
        st.markdown("#### Current Configuration")
        c1, c2, c3, c4 = st.columns(4)
        def metric_card(col, label, value, icon="fa-gear"):
            with col:
                st.markdown(f"""
                <div class="settings-metric">
                  <div style="font-size:0.7rem;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--color-text-muted);margin-bottom:0.4rem;"><i class="fa-solid {icon}"></i>&nbsp; {label}</div>
                  <div style="font-family:var(--font-body);font-size:0.8rem;font-weight:500;color:var(--color-text-secondary);word-break:break-all;">{value}</div>
                </div>
                """, unsafe_allow_html=True)

        if is_cloud:
            masked = (env_api_key[:4] + "****" + env_api_key[-4:]) if len(env_api_key) > 8 else "****"
            metric_card(c1, "API Key", masked, "fa-key")
            metric_card(c2, "Base URL", env_base_url, "fa-server")
            metric_card(c3, "Model", env_model, "fa-microchip")
            metric_card(c4, "SS Key", (env_ss_key[:4] + "****") if len(env_ss_key) > 4 else "not set", "fa-book")
        else:
            key_disp = env.get("api_key", "")
            masked = (key_disp[:4] + "****" + key_disp[-4:]) if len(key_disp) > 8 else "****"
            metric_card(c1, "API Key", masked, "fa-key")
            metric_card(c2, "Base URL", env.get("base_url", ""), "fa-server")
            metric_card(c3, "Model", env.get("model", ""), "fa-microchip")
            ss_d = env.get("ss_api_key", "")
            metric_card(c4, "SS Key", (ss_d[:4] + "****") if len(ss_d) > 4 else "not set", "fa-book")
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_debug:
        st.markdown('<div class="settings-card">', unsafe_allow_html=True)
        st.markdown("<h3>Debug Console</h3>")
        st.caption("Test pipeline components independently before running the full pipeline.")

        # Test 1: Search
        with st.expander("Test 1 — Literature Search", expanded=True):
            sc1, sc2 = st.columns([3, 1])
            with sc1:
                s_query = st.text_input(
                    "Search query",
                    value="LLM reasoning scientific discovery",
                    key="debug_search_query",
                    label_visibility="collapsed",
                )
            with sc2:
                s_btn = st.button("Run", key="btn_search", icon="fa-play")

            if s_btn and s_query:
                st.session_state.debug_search_loading = True
                st.session_state.debug_search_result = None
                st.rerun()

        if st.session_state.get("debug_search_loading"):
            with st.spinner("Searching…"):
                try:
                    from backend.services.search_service import SearchService
                    papers = SearchService().search(s_query, top_k=5)
                    st.session_state.debug_search_result = papers
                except Exception as e:
                    st.session_state.debug_search_result = {"error": str(e)}
                finally:
                    st.session_state.debug_search_loading = False
                    st.rerun()

        s_result = st.session_state.get("debug_search_result")
        if s_result:
            if isinstance(s_result, dict) and "error" in s_result:
                st.error(f"Search failed: {s_result['error']}")
            elif isinstance(s_result, list):
                st.success(f"{len(s_result)} papers found")
                for p in s_result:
                    yr = p.get("year", "?")
                    title = p.get("title", "N/A")[:90]
                    aths = ", ".join(p.get("authors", [])[:3])
                    st.markdown(f"&nbsp;&nbsp;**[{yr}]** {title}", unsafe_allow_html=True)
                    st.caption(f"&nbsp;&nbsp;&nbsp;{aths}")

        st.markdown("<hr style='margin:1.5rem 0'>", unsafe_allow_html=True)

        # Test 2: LLM
        with st.expander("Test 2 — LLM API Call", expanded=True):
            lc1, lc2 = st.columns([3, 1])
            with lc1:
                llm_prompt = st.text_area(
                    "Test prompt",
                    value="Reply with exactly: 'API OK — [model name]'",
                    height=80,
                    key="debug_llm_prompt",
                    label_visibility="collapsed",
                )
            with lc2:
                llm_btn = st.button("Call", key="btn_llm", icon="fa-paper-plane")

            if llm_btn and llm_prompt:
                st.session_state.debug_api_loading = True
                st.session_state.debug_api_result = None
                st.rerun()

        if st.session_state.get("debug_api_loading"):
            with st.spinner("Calling API…"):
                try:
                    from backend.services.llm_service import LLMService
                    resp = LLMService().call("You are a helpful assistant.", llm_prompt, max_tokens=2048, temperature=0.1)
                    st.session_state.debug_api_result = {"success": True, "response": resp}
                except Exception as e:
                    st.session_state.debug_api_result = {"success": False, "error": str(e)}
                finally:
                    st.session_state.debug_api_loading = False
                    st.rerun()

        api_result = st.session_state.get("debug_api_result")
        if api_result:
            if api_result.get("success"):
                st.success("API call succeeded")
                st.markdown(f"**Response:** {api_result['response']}")
            else:
                st.error(f"API call failed: {api_result.get('error', 'Unknown error')}")

        st.markdown("<hr style='margin:1.5rem 0'>", unsafe_allow_html=True)

        # Test 3: Dry run
        with st.expander("Test 3 — Pipeline Dry Run (Search + Write)", expanded=True):
            dc1, dc2 = st.columns([3, 1])
            with dc1:
                dry_topic = st.text_input(
                    "Test topic",
                    value="LLM reasoning in scientific discovery",
                    key="debug_dry_topic",
                    label_visibility="collapsed",
                )
            with dc2:
                dry_btn = st.button("Dry Run", key="btn_dry", icon="fa-bolt",
                                     disabled=st.session_state.get("dry_running", False))

            if dry_btn and dry_topic:
                st.session_state.dry_running = True
                st.session_state.dry_topic = dry_topic
                st.session_state.dry_result = None
                st.rerun()

        if st.session_state.get("dry_running") and not st.session_state.get("dry_result"):
            st.info("Pipeline running (~30s) — please wait…")

        if (st.session_state.get("dry_running")
                and st.session_state.get("dry_result") is None
                and st.session_state.get("dry_topic")):
            topic = st.session_state.get("dry_topic")
            try:
                from backend.services.search_service import SearchService
                from backend.services.citation_service import CitationService
                from agents.writer import WriterAgent
                from backend.services.llm_service import LLMService

                llm = LLMService()
                papers = SearchService().search(topic, top_k=5)

                if not papers:
                    st.session_state.dry_result = {"success": False, "error": "No papers found"}
                else:
                    cs = CitationService(SearchService())
                    for i, paper in enumerate(papers, 1):
                        cs.citation_map[f"[{i}]"] = {
                            "title": paper.get("title", "Unknown"),
                            "paperId": paper.get("paperId", ""),
                            "doi": paper.get("doi"),
                            "year": paper.get("year"),
                            "authors": paper.get("authors", []),
                            "abstract": paper.get("abstract", ""),
                            "url": paper.get("url", ""),
                            "venue": paper.get("venue"),
                            "citationCount": paper.get("citationCount", 0),
                        }
                    abstracts = cs.abstracts_context()
                    writer = WriterAgent(llm)
                    write_result = writer.run(topic, cs.citation_map, abstracts)
                    if write_result.success:
                        st.session_state.dry_result = {
                            "success": True,
                            "data": write_result.content,
                            "papers_count": len(papers),
                        }
                    else:
                        st.session_state.dry_result = {"success": False, "error": write_result.error}
            except Exception as e:
                st.session_state.dry_result = {"success": False, "error": str(e)}
            finally:
                st.session_state.dry_running = False
                st.rerun()

        dry_result = st.session_state.get("dry_result")
        if dry_result:
            st.session_state.dry_running = False
            if dry_result.get("success"):
                data = dry_result["data"]
                count = dry_result.get("papers_count", "?")
                st.success(f"Dry run succeeded — {count} papers processed")
                st.markdown("#### Outline")
                st.markdown(data.get("outline", ""))
                st.markdown("#### Introduction (preview)")
                st.markdown(data.get("introduction", "")[:800] + "…" if data.get("introduction") else "")
            else:
                st.error(f"Dry run failed: {dry_result.get('error', 'Unknown error')}")

        st.markdown("</div>", unsafe_allow_html=True)


# ─── Main ──────────────────────────────────────────
def main():
    pg = st.navigation([
        st.Page(page_main, title="Generate", icon=""),
        st.Page(page_settings, title="Settings", icon=""),
    ])
    pg.run()


if __name__ == "__main__":
    main()
