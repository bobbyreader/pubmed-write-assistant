"""
Streamlit Frontend for AI Paper Tool.
Provides interactive paper generation with multi-round review visibility.
"""

import os
import logging
from datetime import datetime

import streamlit as st

from workflows.writing_pipeline import WritingPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="AI Paper Tool",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ─── Session State ────────────────────────────────────────────
def _init_state():
    defaults = {
        "citation_map": {},
        "topic": "",
        "pipeline_result": None,
        "rounds": [],
        "started": False,
        "error": "",
        "generating": False,
        # Debug state
        "debug_api_result": None,
        "debug_search_result": None,
        "debug_api_loading": False,
        "debug_search_loading": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()


# ─── Helpers ─────────────────────────────────────────────────
def load_env():
    """Load current env vars into session state for the Settings form."""
    from dotenv import load_dotenv
    load_dotenv(override=True)
    return {
        "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "base_url": os.getenv("ANTHROPIC_BASE_URL", "https://api.minimax.chat/v1"),
        "model": os.getenv("ANTHROPIC_MODEL", "MiniMax-M2.7-highspeed"),
    }


def save_env(api_key: str, base_url: str, model: str) -> tuple[bool, str]:
    """Save env vars to .env file."""
    try:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        with open(env_path, "w") as f:
            f.write(f"ANTHROPIC_API_KEY={api_key}\n")
            f.write(f"ANTHROPIC_BASE_URL={base_url}\n")
            f.write(f"ANTHROPIC_MODEL={model}\n")
        # Reload into current process
        os.environ["ANTHROPIC_API_KEY"] = api_key
        os.environ["ANTHROPIC_BASE_URL"] = base_url
        os.environ["ANTHROPIC_MODEL"] = model
        return True, "Saved to .env"
    except Exception as e:
        return False, str(e)


def render_paper_card(cite_id: str, meta: dict):
    """Render a single paper card."""
    title = meta.get("title", "Unknown Title")
    year = meta.get("year", "n.d.")
    authors = meta.get("authors", [])
    if isinstance(authors, list) and authors:
        authors_str = ", ".join(authors[:2])
        if len(authors) > 2:
            authors_str += " et al."
    else:
        authors_str = "Unknown"
    venue = meta.get("venue") or ""
    abstract = meta.get("abstract", "")
    abstract_short = (abstract[:200] + "...") if len(abstract) > 200 else abstract

    with st.expander(f"{cite_id} {title[:60]}{'...' if len(title) > 60 else ''}"):
        st.markdown(f"**{authors_str}** ({year})")
        if venue:
            st.caption(f"📖 {venue}")
        if abstract_short and abstract_short != "Abstract not available.":
            st.info(f"**Abstract:** {abstract_short}")
        paper_id = meta.get("paperId", "")
        if paper_id:
            st.markdown(f"[Semantic Scholar](https://www.semanticscholar.org/paper/{paper_id})")


def render_round_card(record):
    """Render a round record in an expander."""
    phase_icons = {
        "search": "🔍",
        "write": "✍️",
        "review": "🔎",
        "edit": "✏️",
    }
    icon = phase_icons.get(record.phase, "📋")
    label = f"Round {record.round_num} — {icon} {record.phase.capitalize()}"

    with st.expander(label, expanded=(record.phase in ("write", "review"))):
        if record.phase == "search":
            st.success(f"✅ Found papers: {record.notes}")
        elif record.phase == "write":
            if record.draft_content:
                st.markdown("### 📝 Generated Draft")
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
                st.progress(score / 10, text="Quality Score")

                if rc.get("hallucination_flags"):
                    st.error(f"⚠️ Hallucinated citations: {rc['hallucination_flags']}")

                if rc.get("strengths"):
                    with st.expander("✅ Strengths"):
                        for s in rc["strengths"]:
                            st.write(f"- {s}")
                if rc.get("weaknesses"):
                    with st.expander("⚠️ Weaknesses"):
                        for w in rc["weaknesses"]:
                            st.write(f"- {w}")
                if rc.get("suggestions"):
                    with st.expander("💡 Suggestions"):
                        for sg in rc["suggestions"]:
                            st.write(f"- **[{sg.get('section','')}]** {sg.get('suggestion','')}")
                if rc.get("summary"):
                    st.markdown(f"**Summary:** {rc['summary']}")
            if record.error:
                st.error(f"Error: {record.error}")
        elif record.phase == "edit":
            if record.edit_content:
                ec = record.edit_content
                changes = ec.get("changes_made", [])
                st.success(f"Changes made: {', '.join(changes) if changes else 'None'}")
                if ec.get("revised_draft"):
                    with st.expander("📄 Revised Draft"):
                        st.markdown(ec["revised_draft"])
                unresolved = ec.get("unresolved_issues", [])
                if unresolved:
                    st.warning(f"Unresolved: {unresolved}")
            if record.error:
                st.error(f"Error: {record.error}")


# ─── Page: Main ──────────────────────────────────────────────
def page_main():
    st.title("📄 AI Paper Tool")
    st.caption("Generate academic papers with real citations — no hallucinations")

    # ─── Sidebar ─────────────────────────────────────────────
    with st.sidebar:
        st.header("📚 Retrieved Papers")
        citation_map = st.session_state.citation_map
        if citation_map:
            for cite_id, meta in sorted(citation_map.items()):
                render_paper_card(cite_id, meta)
        else:
            st.info("Papers will appear here after search")

        st.divider()
        st.header("⚙️ Quick Settings")
        env = load_env()
        st.text(f"Model: {env['model']}")
        st.text(f"Base URL: {env['base_url']}")
        masked_key = env["api_key"]
        if masked_key and len(masked_key) > 8:
            masked_key = masked_key[:4] + "****" + masked_key[-4:]
        st.text(f"API Key: {masked_key}")

        st.divider()
        if st.button("🗑️ Reset Session"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # ─── Input ───────────────────────────────────────────────
    topic = st.text_input(
        "🔬 Research Topic",
        placeholder="e.g., LLM reasoning in scientific discovery, or 大语言模型在科学发现中的应用",
        help="Enter your research topic in Chinese or English",
    )

    col_generate, _ = st.columns([1, 2])
    with col_generate:
        generate_btn = st.button(
            "🚀 Generate Paper",
            type="primary",
            disabled=st.session_state.generating or not topic.strip(),
        )

    if generate_btn and topic.strip():
        st.session_state.generating = True
        st.session_state.started = True
        st.session_state.topic = topic.strip()
        st.session_state.error = ""
        st.session_state.rounds = []

        try:
            pipeline = WritingPipeline()
            result = pipeline.run(topic.strip())
            st.session_state.pipeline_result = result

            if result.success:
                st.session_state.citation_map = result.citation_map
                st.session_state.rounds = result.rounds
            else:
                st.session_state.error = result.error
        except Exception as e:
            logger.exception("Pipeline failed")
            st.session_state.error = str(e)
        finally:
            st.session_state.generating = False
            st.rerun()

    if st.session_state.generating:
        st.info("⏳ Generating... This may take a few minutes. Please wait...")
        st.progress(None, text="Running pipeline...")

    if st.session_state.error:
        st.error(f"❌ {st.session_state.error}")

    # ─── Results ───────────────────────────────────────────────
    if st.session_state.started and st.session_state.pipeline_result:
        result = st.session_state.pipeline_result

        if result.success:
            st.success(
                f"✅ Done! "
                f"{'🏃 Early exit (high score)' if result.early_exit else f'Completed in {len(result.rounds)} rounds'}"
            )

            tab_draft, tab_refs, tab_history = st.tabs(
                ["📝 Draft", "📚 References", "🔄 Iteration History"]
            )

            with tab_draft:
                st.markdown("### Final Paper")
                if result.final_draft:
                    st.markdown(result.final_draft)
                    md_content = result.final_draft + "\n\n---\n\n## References\n\n" + result.references
                    st.download_button(
                        "📥 Download as Markdown",
                        data=md_content,
                        file_name=f"paper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                        mime="text/markdown",
                    )
                else:
                    st.warning("No draft generated")

            with tab_refs:
                st.markdown("### References")
                st.markdown(result.references)

            with tab_history:
                st.markdown("### Iteration Rounds")
                for record in st.session_state.rounds:
                    render_round_card(record)

    # ─── First-time hint ─────────────────────────────────────
    if not st.session_state.started:
        st.markdown("""
        ### How it works
        1. **Enter** a research topic (Chinese or English)
        2. **Click** Generate Paper
        3. **Download** the final paper as Markdown

        ⚠️ **Anti-hallucination**: All citations are verified against the citation map.
        """)
        st.divider()
        st.caption("Built with MiniMax M2.7 + Semantic Scholar")


# ─── Page: Settings ───────────────────────────────────────────
def page_settings():
    st.title("⚙️ Settings & Debug")

    # ─── Tab: API Config ────────────────────────────────────
    tab_api, tab_debug = st.tabs(["🔑 API Configuration", "🔬 Debug Console"])

    with tab_api:
        st.markdown("### API Configuration")
        st.caption("Changes are saved to `.env` and take effect immediately.")
        st.caption("⚠️ Do not commit `.env` to version control.")

        env = load_env()

        with st.form("env_form", border=True):
            api_key = st.text_input(
                "ANTHROPIC_API_KEY",
                value=env["api_key"],
                type="password",
                help="Your MiniMax API key",
            )
            base_url = st.text_input(
                "ANTHROPIC_BASE_URL",
                value=env["base_url"],
                help="Anthropic-compatible base URL",
            )
            model = st.text_input(
                "ANTHROPIC_MODEL",
                value=env["model"],
                help="Model name (default: MiniMax-M2.7-highspeed)",
            )
            submitted = st.form_submit_button("💾 Save to .env", type="primary")

            if submitted:
                if not api_key.strip():
                    st.error("API key cannot be empty")
                else:
                    ok, msg = save_env(api_key.strip(), base_url.strip(), model.strip())
                    if ok:
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ Failed to save: {msg}")

        # Current config display
        st.markdown("#### Current Configuration")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("API Key", (api_key[:4] + "****" + api_key[-4:]) if len(api_key) > 8 else "****")
        with col2:
            st.metric("Base URL", base_url)
        with col3:
            st.metric("Model", model)

    # ─── Tab: Debug Console ──────────────────────────────────
    with tab_debug:
        st.markdown("### Debug Console")
        st.caption("Test each pipeline component independently before running the full pipeline.")

        # ── 1. Search Test ─────────────────────────────────
        with st.expander("🔍 Test 1: Semantic Scholar Search", expanded=True):
            search_col1, search_col2 = st.columns([3, 1])
            with search_col1:
                search_query = st.text_input(
                    "Search query",
                    value="LLM reasoning scientific discovery",
                    key="debug_search_query",
                    label_visibility="collapsed",
                )
            with search_col2:
                search_btn = st.button("▶️ Run Search", key="btn_search")

            # Show loading indicator before blocking call
            if search_btn and search_query:
                st.session_state.debug_search_loading = True
                st.session_state.debug_search_result = None
                st.rerun()

        # Loading / result state (rendered after rerun)
        if st.session_state.get("debug_search_loading"):
            with st.spinner("🔍 Searching Semantic Scholar (timeout 15s)..."):
                try:
                    from backend.services.search_service import SearchService
                    ss = SearchService()
                    papers = ss.search(search_query, top_k=3)
                    st.session_state.debug_search_result = papers
                except Exception as e:
                    st.session_state.debug_search_result = {"error": str(e)}
                finally:
                    st.session_state.debug_search_loading = False
                    st.rerun()

        result = st.session_state.get("debug_search_result")
        if result:
            if isinstance(result, dict) and "error" in result:
                st.error(f"Search failed: {result['error']}")
            elif isinstance(result, list):
                st.success(f"✅ Search returned {len(result)} papers")
                for p in result:
                    st.markdown(f"**[{p.get('year','?')}]** {p.get('title', 'N/A')[:80]}")
                    st.caption(f"   Authors: {', '.join(p.get('authors', [])[:3])}")

        st.divider()

        # ── 2. LLM API Test ─────────────────────────────────
        with st.expander("🤖 Test 2: LLM API (MiniMax M2.7)", expanded=True):
            llm_col1, llm_col2 = st.columns([3, 1])
            with llm_col1:
                llm_prompt = st.text_area(
                    "Test prompt",
                    value="Reply with exactly: 'API OK: [your model name]'",
                    height=80,
                    key="debug_llm_prompt",
                    label_visibility="collapsed",
                )
            with llm_col2:
                llm_btn = st.button("▶️ Call API", key="btn_llm")

            if llm_btn and llm_prompt:
                st.session_state.debug_api_loading = True
                st.session_state.debug_api_result = None
                st.rerun()

        # Loading / result state
        if st.session_state.get("debug_api_loading"):
            llm_prompt = st.session_state.get("debug_llm_prompt", "")
            with st.spinner("🤖 Calling LLM API..."):
                try:
                    from backend.services.llm_service import LLMService
                    llm = LLMService()
                    response = llm.call(
                        system_prompt="You are a helpful assistant.",
                        user_prompt=llm_prompt,
                        max_tokens=2048,
                        temperature=0.1,
                    )
                    st.session_state.debug_api_result = {"success": True, "response": response}
                except Exception as e:
                    st.session_state.debug_api_result = {"success": False, "error": str(e)}
                finally:
                    st.session_state.debug_api_loading = False
                    st.rerun()

        api_result = st.session_state.get("debug_api_result")
        if api_result:
            if api_result.get("success"):
                st.success("✅ API call succeeded")
                st.markdown(f"**Response:**\n\n{api_result['response']}")
            else:
                st.error(f"❌ API call failed: {api_result.get('error', 'Unknown error')}")

        st.divider()

        # ── 3. Pipeline Dry Run ─────────────────────────────
        with st.expander("⚡ Test 3: Mini Pipeline (Search + Write only)", expanded=True):
            st.caption("Run a lightweight version of the pipeline (~30-40s). Shows results when done.")
            dry_col1, dry_col2 = st.columns([3, 1])
            with dry_col1:
                dry_topic_input = st.text_input(
                    "Test topic",
                    value="LLM reasoning in scientific discovery",
                    key="debug_dry_topic",
                    label_visibility="collapsed",
                )
            with dry_col2:
                dry_btn = st.button(
                    "▶️ Dry Run",
                    key="btn_dry",
                    disabled=st.session_state.get("dry_running", False),
                )

            # Button clicked → set state and rerun
            if dry_btn and dry_topic_input:
                st.session_state.dry_running = True
                st.session_state.dry_topic = dry_topic_input
                st.session_state.dry_result = None
                st.rerun()

            # Show running indicator when pipeline is active
            if st.session_state.get("dry_running") and not st.session_state.get("dry_result"):
                st.info("🤖 Pipeline running (~30s) — please wait...")

            # Pipeline execution on rerun after button click
            if (st.session_state.get("dry_running") and
                    st.session_state.get("dry_result") is None and
                    st.session_state.get("dry_topic")):
                topic = st.session_state.get("dry_topic")
                try:
                    from backend.services.search_service import SearchService
                    from backend.services.citation_service import CitationService
                    from agents.writer import WriterAgent
                    from backend.services.llm_service import LLMService

                    llm = LLMService()
                    ss = SearchService()

                    # Search
                    papers = ss.search(topic, top_k=5)

                    if not papers:
                        st.session_state.dry_result = {"success": False, "error": "No papers found"}
                    else:
                        # Build citation map
                        cs = CitationService(ss)
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

                        # Write
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

            # Display results
            dry_result = st.session_state.get("dry_result")
            if dry_result:
                st.session_state.dry_running = False  # ensure button re-enabled
                if dry_result.get("success"):
                    data = dry_result["data"]
                    count = dry_result.get("papers_count", "?")
                    st.success(f"✅ Dry run succeeded — {count} papers processed")
                    st.markdown("#### Outline")
                    st.markdown(data.get("outline", ""))
                    st.markdown("#### Introduction (preview)")
                    st.markdown(data.get("introduction", "")[:1000])
                else:
                    st.error(f"❌ Dry run failed: {dry_result.get('error', 'Unknown error')}")


# ─── Main ────────────────────────────────────────────────────
def main():
    st.title("📄 AI Paper Tool")
    st.caption("Generate academic papers with real citations — no hallucinations")

    # Top nav
    pg = st.navigation([
        st.Page(page_main, title="📝 Generate Paper", icon="📝"),
        st.Page(page_settings, title="⚙️ Settings & Debug", icon="⚙️"),
    ])
    pg.run()


if __name__ == "__main__":
    main()
