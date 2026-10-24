"""
Streamlit Frontend for AI Paper Tool.
Apple Design System — Clean, cinematic, binary light/dark rhythm.
BUILD: 2026-10-24T15:20+08:00
"""
import os
import hmac
import logging
import threading
import queue
import time
from datetime import datetime
from typing import Optional

import streamlit as st

from workflows.writing_pipeline_with_checkpoint import WritingPipelineWithCheckpoint
from utils.export_service import export_word, export_pdf
from backend.services.metrics_service import MetricsService
from utils.i18n import t, get_lang, render_lang_toggle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="PubMed Paper Assistant",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── External Resources ──────────────────────────────
# SF Pro via system fonts — no external CDN needed for Apple system fonts
# Material Icons for icon accents
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Material+Icons" rel="stylesheet">
""", unsafe_allow_html=True)

# Custom CSS — served from static/ to bypass Render build cache
with open(os.path.join(os.path.dirname(__file__), "static", "css", "apple.css")) as f:
    st.html(f'<style>{f.read()}</style>')


# ─── Session State ─────────────────────────────────
def _init_state():
    defaults = {
        "lang": "zh",
    "citation_map": {},
        "topic": "",
        "seed_papers": [],
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
        "enable_checkpoint": True,
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
    abstract_short = (abstract[:140] + "…") if len(abstract) > 140 else abstract
    if abstract_short == "Abstract not available.":
        abstract_short = ""

    url = meta.get("url", "")
    label = t("view_pubmed") if "pubmed" in url else t("view_source")

    st.markdown(f"""
    <div class="apple-paper-card">
      <div class="apple-paper-title">{cite_id} {title[:65]}{'…' if len(title) > 65 else ''}</div>
      <div class="apple-paper-meta">{authors_str} &middot; {year}{' &middot; ' + venue if venue else ''}</div>
      {f'<div class="apple-paper-abstract">{abstract_short}</div>' if abstract_short else ''}
      {f'<a class="apple-paper-link" href="{url}" target="_blank"><i class="material-icons" style="font-size:0.8rem;vertical-align:middle;margin-right:2px;">open_in_new</i>{label}</a>' if url else ''}
    </div>
    """, unsafe_allow_html=True)


# ─── Render: Round Card ───────────────────────────
def render_round_card(record):
    phase_labels = {
        "search": t("phase_search"),
        "write": t("phase_write"),
        "review": t("phase_review"),
        "edit": t("phase_edit"),
    }
    phase_icons = {
        "search": "manage_search",
        "write": "edit_note",
        "review": "visibility",
        "edit": "draw",
    }
    icon = phase_icons.get(record.phase, "circle")
    label = phase_labels.get(record.phase, record.phase.capitalize())

    st.markdown(f"""
    <div class="apple-round-card">
      <div class="apple-round-label">
        <i class="material-icons" style="font-size:0.85rem;vertical-align:middle;">{icon}</i>
        {t("round_label", n=record.round_num)} &mdash; {label}
      </div>
    """, unsafe_allow_html=True)

    if record.phase == "search":
        st.markdown(f'<div class="apple-progress-text"><i class="material-icons" style="font-size:0.9rem;vertical-align:middle;margin-right:4px;color:#248a3d;">check_circle</i> {record.notes}</div>')

    elif record.phase == "write":
        if record.draft_content:
            st.markdown(t("generated_draft"))
            st.markdown(record.draft_content)

    elif record.phase == "review":
        if record.review_content:
            rc = record.review_content
            score = rc.get("score", 0)
            cite_acc = rc.get("citation_accuracy_score", 10)
            col1, col2 = st.columns(2)
            with col1:
                st.metric(t("overall_score"), f"{score}/10")
            with col2:
                st.metric(t("citation_accuracy"), f"{cite_acc}/10")
            st.progress(score / 10, text=t("quality_score", score=score))

            if rc.get("hallucination_flags"):
                flags_str = ', '.join(str(f) for f in rc['hallucination_flags'])
                st.error(t("hallucination", flags=flags_str))

            if rc.get("strengths"):
                with st.expander(t("strengths")):
                    for s in rc["strengths"]:
                        st.write(f"&nbsp;&nbsp;&nbsp;{s}")
            if rc.get("weaknesses"):
                with st.expander(t("improvements")):
                    for w in rc["weaknesses"]:
                        st.write(f"&nbsp;&nbsp;&nbsp;{w}")
            if rc.get("suggestions"):
                with st.expander(t("suggestions")):
                    for sg in rc["suggestions"]:
                        if isinstance(sg, dict):
                            st.write(f"**{sg.get('section', '')}** — {sg.get('suggestion', '')}")
                        else:
                            st.write(f"&nbsp;&nbsp;&nbsp;{sg}")
            if rc.get("summary"):
                st.markdown(t("reviewer_summary", summary=rc['summary']))
        if record.error:
            st.error(t("error_prefix", e=record.error))

    elif record.phase == "edit":
        if record.edit_content:
            ec = record.edit_content
            changes = ec.get("changes_made", [])
            if changes:
                st.success(t("changes_applied", changes=', '.join(changes)))
            else:
                st.success(t("no_changes"))
            if ec.get("revised_draft"):
                with st.expander(t("revised_draft")):
                    st.markdown(ec["revised_draft"])
            unresolved = ec.get("unresolved_issues", [])
            if unresolved:
                st.warning(t("unresolved", items=', '.join(unresolved)))
        if record.error:
            st.error(t("error_prefix", e=record.error))

    st.markdown("</div>")


# ─── Page: Main ────────────────────────────────────
def page_main():
    # ─── Hero Section ─────────────────────────────
    # NOTE: the whole hero must be ONE st.markdown call — Streamlit closes
    # HTML tags within each call, so a div opened in one call never wraps
    # elements from later calls (it renders as an empty panel).
    st.markdown(f"""
    <div class="apple-hero-section">
      <div class="apple-hero-eyebrow">{t("hero_eyebrow")}</div>
      <h1 class="apple-hero-title">{t("hero_title")}</h1>
      <p class="apple-body apple-hero-sub">{t("hero_sub")}</p>
    </div>
    """, unsafe_allow_html=True)

    # ─── Sidebar ─────────────────────────────────────
    with st.sidebar:
        st.markdown(f'<div class="apple-divider-label">{t("sb_retrieved")}</div>', unsafe_allow_html=True)
        citation_map = st.session_state.citation_map
        if citation_map:
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric(t("sb_papers"), len(citation_map))
            with col_b:
                st.metric(t("sb_citations"), len(citation_map))
            st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
            for cite_id, meta in sorted(citation_map.items()):
                render_paper_card(cite_id, meta)
        else:
            st.metric(t("sb_papers"), 0)
            st.markdown(f"""
            <div class="apple-empty-state">
              <i class="material-icons" style="font-size:1.5rem;color:var(--apple-black-48);">folder_open</i>
              <span class="apple-caption">{t("sb_search_hint")}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<hr>', unsafe_allow_html=True)
        st.markdown(f'<div class="apple-divider-label">{t("sb_config")}</div>', unsafe_allow_html=True)
        env = load_env()
        st.markdown(f'<div class="apple-paper-meta">{t("sb_model")}: <strong>{env["model"]}</strong></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="apple-paper-meta" style="word-break:break-all">{t("sb_endpoint")}: {env["base_url"]}</div>', unsafe_allow_html=True)
        is_cloud = bool(os.getenv("ANTHROPIC_API_KEY", ""))
        if is_cloud:
            st.markdown(f'<div class="apple-paper-meta" style="color:#248a3d;"><i class="material-icons" style="font-size:0.75rem;vertical-align:middle;margin-right:3px;">lock</i>{t("sb_key_env")}</div>', unsafe_allow_html=True)
        else:
            key = env["api_key"]
            masked = (key[:4] + "****" + key[-4:]) if len(key) > 8 else "****"
            st.markdown(f'<div class="apple-paper-meta">{t("sb_api_key")}: {masked}</div>', unsafe_allow_html=True)

        st.markdown('<hr>', unsafe_allow_html=True)
        if st.button(t("sb_reset"), use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # ─── Composer: topic + filters in one card ─────
    with st.container(key="composer"):
        st.markdown(f'<div class="apple-composer-label">{t("composer_label")}</div>', unsafe_allow_html=True)
        topic = st.text_input(
            "",
            placeholder=t("topic_placeholder"),
            label_visibility="collapsed",
            key="hero_topic_input",
        )

        col1, col2, col3 = st.columns([1.5, 1, 1])
        with col1:
            # A: big live value badge beside the slider — the built-in
            # slider value is tiny grey text that is easy to miss while
            # dragging, so the current value gets its own large readout.
            scol, vcol = st.columns([3, 1])
            with scol:
                search_top_k = st.slider(t("filter_papers"), min_value=5, max_value=50, value=20, step=5)
            with vcol:
                st.markdown(
                    f'<div class="apple-slider-value">{search_top_k}<span>{t("papers_unit")}</span></div>',
                    unsafe_allow_html=True,
                )
        with col2:
            year_from = st.number_input(t("year_from"), min_value=1990, max_value=2026, value=2018)
        with col3:
            year_to = st.number_input(t("year_to"), min_value=1990, max_value=2026, value=2026)

        col4, col5 = st.columns(2)
        with col4:
            author = st.text_input(t("author_label"), placeholder=t("author_ph"))
        with col5:
            venue = st.text_input(t("venue_label"), placeholder=t("venue_ph"))


    # Seed papers: import research-assistant favorites backup (optional)
    with st.expander(t("seed_title")):
        st.caption(t("seed_caption"))
        seed_file = st.file_uploader(t("seed_upload_label"), type=["json"], key="seed_upload")
        if seed_file is not None:
            sig = f"{seed_file.name}:{seed_file.size}"
            if st.session_state.get("seed_file_sig") != sig:
                try:
                    import json as _json
                    from backend.services.favorites_import import parse_favorites_backup, enrich_abstracts
                    data = _json.loads(seed_file.getvalue().decode("utf-8"))
                    papers = parse_favorites_backup(data)
                    with st.spinner(t("seed_importing")):
                        papers = enrich_abstracts(papers)
                    st.session_state.seed_papers = papers
                    st.session_state.seed_file_sig = sig
                    st.success(t("seed_imported", n=len(papers)))
                except Exception as e:
                    st.error(t("seed_failed", e=e))
        if st.session_state.get("seed_papers"):
            st.write(t("seed_current", n=len(st.session_state.seed_papers)))
            for _p in st.session_state.seed_papers[:5]:
                st.caption(f"• {_p.get('title', '')}（{_p.get('year') or t('seed_year_unknown')}）")
            if len(st.session_state.seed_papers) > 5:
                st.caption(t("seed_more", n=len(st.session_state.seed_papers)))
            if st.button(t("seed_clear")):
                st.session_state.seed_papers = []
                st.session_state.seed_file_sig = ""
                st.rerun()

    # Advanced settings
    with st.expander(t("adv_title")):
        st.checkbox(
            t("adv_checkpoint"),
            value=True,
            key="enable_checkpoint",
            help=t("adv_checkpoint_help"),
        )

    st.markdown("")

    # ─── Generate Button ───────────────────────────
    disabled = st.session_state.generating or not topic.strip()
    if st.button(t("gen_button"), type="primary", disabled=disabled, use_container_width=True):
        st.session_state.generating = True
        st.session_state.generating_done = False
        st.session_state.started = True
        st.session_state.topic = topic.strip()
        st.session_state.error = ""
        st.session_state.rounds = []
        st.session_state.pipeline_result = None
        st.session_state.citation_map = {}
        st.session_state.pipeline_progress_phase = "init"
        st.session_state.pipeline_progress_msg = t("gen_starting")
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
            seeds_in: Optional[list] = None,
            lang_in: str = "zh",
        ):
            try:
                pl = WritingPipelineWithCheckpoint(enable_checkpoint=st.session_state.get('enable_checkpoint', True))
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
                    seed_papers=seeds_in or None,
                    lang=lang_in,
                )
                q_out.put(("result", result))
            except Exception as e:
                logger.exception("Pipeline thread failed")
                q_out.put(("error", str(e)))

        thread = threading.Thread(
            target=_run_pipeline,
            args=(
                q,
                topic.strip(),
                search_top_k,
                year_from,
                year_to,
                author if (author or "").strip() else None,
                venue if (venue or "").strip() else None,
                list(st.session_state.get("seed_papers") or []),
                get_lang(),
            ),
            daemon=True,
        )
        thread.start()
        st.rerun()

    # ─── Progress Display ───────────────────────────
    # Always show when generating (even mid-poll)
    if st.session_state.generating:
        phase = st.session_state.pipeline_progress_phase
        msg = st.session_state.pipeline_progress_msg
        frac = st.session_state.pipeline_progress_fraction
        phase_icons = {
            "init": "settings",
            "research": "manage_search",
            "write": "edit_note",
            "review": "visibility",
            "edit": "draw",
            "finalize": "save",
        }
        icon = phase_icons.get(phase, "spinner")
        spin_animate = "animation:spin 1.5s linear infinite;" if phase in ("init", "research", "write") else ""
        st.markdown(f"""
        <div class="apple-progress-wrapper">
          <div class="apple-progress-text">
            <i class="material-icons" style="font-size:1rem;vertical-align:middle;margin-right:6px;{spin_animate}">{icon}</i>
            {msg}
          </div>
        </div>
        """, unsafe_allow_html=True)
        st.progress(max(0.0, min(1.0, frac or 0)))

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

    if st.session_state.error:
        st.error(st.session_state.error)

    # ─── Results ───────────────────────────────────
    if st.session_state.started and st.session_state.pipeline_result:
        result = st.session_state.pipeline_result

        if result.success:
            early = t("done_early") if result.early_exit else t("done_rounds", n=len(result.rounds))
            if result.resumed_from_checkpoint:
                st.info(t("resumed"))
            st.success(f"{t('done')} — {early}")

            tab1, tab2, tab3, tab4 = st.tabs([
                t("tab_draft"),
                t("tab_refs"),
                t("tab_history"),
                t("tab_usage"),
            ])

            with tab1:
                st.markdown(t("final_paper"))
                if result.final_draft:
                    st.markdown(result.final_draft)
                    md_content = result.final_draft + "\n\n---\n\n" + t("refs_heading_md") + "\n\n" + result.references
                    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

                    d1, d2, d3 = st.columns([1, 1, 1])
                    with d1:
                        st.download_button(
                            "Markdown",
                            data=md_content,
                            file_name=f"paper_{ts}.md",
                            mime="text/markdown",
                        )
                    with d2:
                        st.download_button(
                            "Word",
                            data=export_word(md_content, st.session_state.topic),
                            file_name=f"paper_{ts}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    with d3:
                        st.download_button(
                            "PDF",
                            data=export_pdf(md_content, st.session_state.topic),
                            file_name=f"paper_{ts}.pdf",
                            mime="application/pdf",
                        )
                else:
                    st.warning(t("no_draft"))

            with tab2:
                st.markdown(t("refs_title"))
                st.markdown(result.references)

            with tab3:
                st.markdown(t("rounds_title"))
                for record in st.session_state.rounds:
                    render_round_card(record)

            with tab4:
                st.markdown(t("usage_title"))
                metrics = MetricsService()
                summary = metrics.get_session_summary()
                
                # Summary cards
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(t("m_total_calls"), summary.total_calls)
                c2.metric(t("m_success_rate"), f"{summary.successful_calls/max(summary.total_calls,1)*100:.1f}%")
                c3.metric(t("m_total_tokens"), f"{summary.total_tokens:,}")
                c4.metric(t("m_duration"), f"{summary.total_duration_ms/1000:.1f}s")
                
                # Token breakdown
                st.markdown(t("token_breakdown"))
                tc1, tc2 = st.columns(2)
                tc1.metric(t("m_in_tokens"), f"{summary.total_input_tokens:,}")
                tc2.metric(t("m_out_tokens"), f"{summary.total_output_tokens:,}")
                
                # By agent
                if summary.calls_by_agent:
                    st.markdown(t("usage_by_agent"))
                    for agent, stats in sorted(summary.calls_by_agent.items()):
                        st.markdown(t("agent_usage_line", agent=agent, calls=stats["calls"], tokens=f"{stats['tokens']:,}"))
                
                # Errors
                if summary.errors:
                    st.markdown(t("errors_title"))
                    for err in summary.errors[:5]:
                        st.error(err[:200])

    # ─── Onboarding (Apple "How it works") ──────────
    if not st.session_state.started:
        st.markdown(f"""
        <div class="apple-how-it-works">
          <h3>{t("how_title")}</h3>
          <ol>
            <li>{t("how_1")}</li>
            <li>{t("how_2")}</li>
            <li>{t("how_3")}</li>
          </ol>
          <div class="apple-info-strip">
            <i class="material-icons" style="font-size:1rem;vertical-align:middle;">shield</i>
            <span>{t("how_shield")}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)


# ─── Page: Settings ─────────────────────────────────
def page_settings():
    st.markdown(f'<h1 class="apple-section-title">{t("set_title")}</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="apple-body">{t("set_sub")}</p>', unsafe_allow_html=True)

    tab_api, tab_debug = st.tabs([t("tab_api"), t("tab_debug")])

    with tab_api:
        st.markdown('<div class="apple-settings-card">', unsafe_allow_html=True)
        st.markdown(f"<h3>{t('api_card_title')}</h3>", unsafe_allow_html=True)

        env_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        env_base_url = os.getenv("ANTHROPIC_BASE_URL", "")
        env_model = os.getenv("ANTHROPIC_MODEL", "")
        env_ss_key = os.getenv("SEMANTICSCHOLAR_API_KEY", "")
        is_cloud = bool(env_api_key)

        if is_cloud:
            st.success(t("cloud_ok"))
        else:
            st.caption(t("local_caption"))

        env = load_env()

        with st.form("env_form", border=True):
            if is_cloud:
                st.text_input("ANTHROPIC_API_KEY", value="•" * 20, disabled=True, help=t("help_env_var"))
                st.text_input("ANTHROPIC_BASE_URL", value=env_base_url, disabled=True)
                st.text_input("ANTHROPIC_MODEL", value=env_model, disabled=True)
                st.text_input(t("ss_optional"), value="•" * 20 if env_ss_key else "", disabled=True)
                st.info(t("env_readonly"))
                st.form_submit_button(t("save_env"), disabled=True)
            else:
                api_key = st.text_input("ANTHROPIC_API_KEY", value=env["api_key"], type="password", help="MiniMax API key")
                base_url = st.text_input("ANTHROPIC_BASE_URL", value=env["base_url"], help=t("help_base_url"))
                model = st.text_input("ANTHROPIC_MODEL", value=env["model"], help=t("help_model"))
                ss_api_key = st.text_input("SEMANTICSCHOLAR_API_KEY (optional)", value=env.get("ss_api_key", ""), type="password", help="Semantic Scholar API key — increases rate limit. Free at semanticscholar.org")
                st.form_submit_button(t("save_env"))

        # Current config display
        st.markdown(t("current_config"))
        c1, c2, c3, c4 = st.columns(4)

        def metric_card(col, label, value, icon="settings"):
            with col:
                st.markdown(f"""
                <div class="apple-settings-metric">
                  <div style="font-size:0.75rem;font-weight:600;letter-spacing:-0.12px;text-transform:uppercase;color:var(--apple-black-48);margin-bottom:var(--sp-5);display:flex;align-items:center;gap:4px;">
                    <i class="material-icons" style="font-size:0.8rem;vertical-align:middle;">{icon}</i>{label}
                  </div>
                  <div style="font-family:var(--font-text);font-size:0.85rem;font-weight:400;color:var(--apple-black-80);word-break:break-all;">{value}</div>
                </div>
                """, unsafe_allow_html=True)

        if is_cloud:
            masked = (env_api_key[:4] + "****" + env_api_key[-4:]) if len(env_api_key) > 8 else "****"
            metric_card(c1, t("api_key_label"), masked, "vpn_key")
            metric_card(c2, t("base_url_label"), env_base_url, "cloud")
            metric_card(c3, t("model_label"), env_model, "memory")
            metric_card(c4, t("ss_key_label"), (env_ss_key[:4] + "****") if len(env_ss_key) > 4 else t("not_set"), "menu_book")
        else:
            key_disp = env.get("api_key", "")
            masked = (key_disp[:4] + "****" + key_disp[-4:]) if len(key_disp) > 8 else "****"
            metric_card(c1, t("api_key_label"), masked, "vpn_key")
            metric_card(c2, t("base_url_label"), env.get("base_url", ""), "cloud")
            metric_card(c3, t("model_label"), env.get("model", ""), "memory")
            ss_d = env.get("ss_api_key", "")
            metric_card(c4, t("ss_key_label"), (ss_d[:4] + "****") if len(ss_d) > 4 else t("not_set"), "menu_book")
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_debug:
        st.markdown('<div class="apple-settings-card">', unsafe_allow_html=True)
        st.markdown(f"<h3>{t('dbg_title')}</h3>")
        st.caption(t("dbg_caption"))

        # Test 1: Search
        with st.expander(t("test1_title"), expanded=True):
            sc1, sc2 = st.columns([3, 1])
            with sc1:
                s_query = st.text_input(
                    t("search_query_ph"),
                    value="LLM reasoning scientific discovery",
                    key="debug_search_query",
                    label_visibility="collapsed",
                )
            with sc2:
                s_btn = st.button(t("run"), key="btn_search")

            if s_btn and s_query:
                st.session_state.debug_search_loading = True
                st.session_state.debug_search_result = None
                st.rerun()

        if st.session_state.get("debug_search_loading"):
            with st.spinner(t("searching")):
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
                st.error(t("search_failed", e=s_result['error']))
            elif isinstance(s_result, list):
                st.success(t("papers_found", n=len(s_result)))
                for p in s_result:
                    yr = p.get("year", "?")
                    title = p.get("title", "N/A")[:90]
                    aths = ", ".join(p.get("authors", [])[:3])
                    st.markdown(f"&nbsp;&nbsp;**[{yr}]** {title}")
                    st.caption(f"&nbsp;&nbsp;&nbsp;{aths}")

        st.markdown("<hr style='margin:1.5rem 0'>", unsafe_allow_html=True)

        # Test 2: LLM
        with st.expander(t("test2_title"), expanded=True):
            lc1, lc2 = st.columns([3, 1])
            with lc1:
                llm_prompt = st.text_area(
                    t("test_prompt_label"),
                    value="Reply with exactly: 'API OK — [model name]'",
                    height=80,
                    key="debug_llm_prompt",
                    label_visibility="collapsed",
                )
            with lc2:
                llm_btn = st.button(t("call"), key="btn_llm")

            if llm_btn and llm_prompt:
                st.session_state.debug_api_loading = True
                st.session_state.debug_api_result = None
                st.rerun()

        if st.session_state.get("debug_api_loading"):
            with st.spinner(t("calling")):
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
                st.success(t("api_ok"))
                st.markdown(t("response_label", resp=api_result['response']))
            else:
                st.error(t("api_failed", e=api_result.get('error') or t("unknown_error")))

        st.markdown("<hr style='margin:1.5rem 0'>", unsafe_allow_html=True)

        # Test 3: Dry run
        with st.expander(t("test3_title"), expanded=True):
            dc1, dc2 = st.columns([3, 1])
            with dc1:
                dry_topic = st.text_input(
                    t("test_topic_label"),
                    value="LLM reasoning in scientific discovery",
                    key="debug_dry_topic",
                    label_visibility="collapsed",
                )
            with dc2:
                dry_btn = st.button(t("dry_run"), key="btn_dry",
                                     disabled=st.session_state.get("dry_running", False))

            if dry_btn and dry_topic:
                st.session_state.dry_running = True
                st.session_state.dry_topic = dry_topic
                st.session_state.dry_result = None
                st.rerun()

        if st.session_state.get("dry_running") and not st.session_state.get("dry_result"):
            st.info(t("dry_running_msg"))

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
                    st.session_state.dry_result = {"success": False, "error": t("dry_no_papers")}
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
                st.success(t("dry_succeeded", n=count))
                st.markdown(t("dry_outline"))
                st.markdown(data.get("outline", ""))
                st.markdown(t("dry_intro"))
                st.markdown(data.get("introduction", "")[:800] + "…" if data.get("introduction") else "")
            else:
                st.error(t("dry_failed", e=dry_result.get('error') or t("unknown_error")))

        st.markdown("</div>", unsafe_allow_html=True)


# ─── Access Gate ───────────────────────────────────
def require_access():
    """Password gate, active only when the APP_PASSWORD env var is set
    (e.g. on Render). Local runs without it stay open."""
    password = os.getenv("APP_PASSWORD", "")
    if not password:
        return
    if st.session_state.get("access_granted"):
        return
    # Gate block lives in a keyed container so CSS can center the whole
    # prompt + input block in the viewport (.st-key-gate).
    with st.container(key="gate"):
        st.title(t("gate_title"))
        st.caption(t("gate_caption"))
        with st.form("access_form"):
            entered = st.text_input(t("gate_label"), type="password")
            submitted = st.form_submit_button(t("gate_enter"))
        if submitted:
            if hmac.compare_digest(entered, password):
                st.session_state["access_granted"] = True
                st.rerun()
            else:
                st.error(t("gate_wrong"))
    st.stop()


# ─── Main ──────────────────────────────────────────
def main():
    render_lang_toggle()
    require_access()
    if not os.getenv("APP_PASSWORD"):
        st.sidebar.warning(t("no_password_warn"))
    pg = st.navigation([
        st.Page(page_main, title=t("nav_generate")),
        st.Page(page_settings, title=t("nav_settings")),
    ])
    pg.run()


if __name__ == "__main__":
    main()
