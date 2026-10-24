"""
UI internationalization — Simplified Chinese (default) / English.

The frontend language lives in st.session_state["lang"] and is switched by
a fixed top-right segmented control (中文 / EN), rendered in main()
before the access gate so it is available on every page.

`t(key, **fmt)`   — UI strings (needs Streamlit session state).
`pm(key, lang, **fmt)` — pipeline progress/error strings; pure function,
safe to call from the pipeline worker thread (no session context there).
"""

import streamlit as st

LANGS = ("zh", "en")
DEFAULT_LANG = "zh"

STRINGS: dict[str, dict[str, str]] = {
    # ─── Navigation / gate ───
    "nav_generate": {"zh": "生成论文", "en": "Generate"},
    "nav_settings": {"zh": "设置", "en": "Settings"},
    "gate_title": {"zh": "🔒 需要访问口令", "en": "🔒 Access Password Required"},
    "gate_caption": {"zh": "此部署已启用访问保护，请输入口令继续。",
                     "en": "This deployment is password-protected. Enter the password to continue."},
    "gate_label": {"zh": "访问口令", "en": "Password"},
    "gate_enter": {"zh": "进入", "en": "Enter"},
    "gate_wrong": {"zh": "口令不正确，请重试。", "en": "Incorrect password, please try again."},
    "no_password_warn": {"zh": "⚠️ 未设置 APP_PASSWORD 环境变量：当前为开放访问，任何打开链接的人都能使用本部署并消耗 API 额度。",
                         "en": "⚠️ APP_PASSWORD is not set: this deployment is openly accessible and anyone with the link can use it and consume API quota."},
    # ─── Hero ───
    "hero_eyebrow": {"zh": "AI 科研论文写作", "en": "AI Research Paper Writer"},
    "hero_title": {"zh": "PubMed 论文写作助手", "en": "PubMed Paper Assistant"},
    "hero_sub": {"zh": "生成可发表级的研究论文，全部引用经真实文献核验 —— 由 AI 驱动，以事实为准绳。",
                 "en": "Generate publication-ready research papers with verified citations — powered by AI, constrained by truth."},
    # ─── Sidebar ───
    "sb_retrieved": {"zh": "已检索文献", "en": "Retrieved Papers"},
    "sb_papers": {"zh": "文献", "en": "Papers"},
    "sb_citations": {"zh": "引用", "en": "Citations"},
    "sb_search_hint": {"zh": "搜索后在此显示文献", "en": "Search to retrieve papers"},
    "sb_config": {"zh": "配置", "en": "Configuration"},
    "sb_model": {"zh": "模型", "en": "Model"},
    "sb_endpoint": {"zh": "接口", "en": "Endpoint"},
    "sb_key_env": {"zh": "API 密钥来自环境变量", "en": "API key via environment"},
    "sb_api_key": {"zh": "API 密钥", "en": "API Key"},
    "sb_reset": {"zh": "重置会话", "en": "Reset Session"},
    "view_pubmed": {"zh": "在 PubMed 查看", "en": "View on PubMed"},
    "view_source": {"zh": "查看来源", "en": "View Source"},
    # ─── Composer / filters ───
    "composer_label": {"zh": "研究主题", "en": "Research Topic"},
    "topic_placeholder": {"zh": "输入研究主题 — 例如：大语言模型在科学发现中的推理",
                          "en": "Search research topic — e.g. LLM reasoning in scientific discovery"},
    "filter_papers": {"zh": "检索文献数", "en": "Papers to retrieve"},
    "year_from": {"zh": "起始年份", "en": "Year from"},
    "year_to": {"zh": "结束年份", "en": "Year to"},
    "author_label": {"zh": "作者", "en": "Author"},
    "author_ph": {"zh": "不限作者", "en": "Any author"},
    "venue_label": {"zh": "期刊 / 来源", "en": "Journal / Venue"},
    "venue_ph": {"zh": "不限期刊", "en": "Any journal"},
    # ─── Seed papers ───
    "seed_title": {"zh": "📥 种子文献：导入研究助手收藏（可选）",
                   "en": "📥 Seed papers: import research-assistant favorites (optional)"},
    "seed_caption": {"zh": "在 PubMed 研究助手里点「导出备份 (JSON)」得到的文件可直接导入。导入后将跳过在线检索、直接以收藏作为种子文献写作，并自动从 PubMed 补齐摘要。",
                     "en": "Export a backup JSON from the PubMed research assistant and import it here. The pipeline then skips online search, writes from your favorites directly, and fills in abstracts from PubMed automatically."},
    "seed_upload_label": {"zh": "选择收藏备份 JSON", "en": "Choose favorites backup JSON"},
    "seed_importing": {"zh": "正在从 PubMed 补齐摘要…", "en": "Fetching abstracts from PubMed…"},
    "seed_imported": {"zh": "已导入 {n} 篇种子文献", "en": "Imported {n} seed papers"},
    "seed_failed": {"zh": "导入失败：{e}", "en": "Import failed: {e}"},
    "seed_current": {"zh": "当前种子文献：{n} 篇", "en": "Seed papers loaded: {n}"},
    "seed_year_unknown": {"zh": "年份未知", "en": "year unknown"},
    "seed_more": {"zh": "……等共 {n} 篇", "en": "… {n} papers in total"},
    "seed_clear": {"zh": "清除种子文献", "en": "Clear seed papers"},
    # ─── Advanced / generate ───
    "adv_title": {"zh": "高级设置", "en": "Advanced Settings"},
    "adv_checkpoint": {"zh": "启用断点保存（中断后可恢复）", "en": "Enable checkpoint saving (resume on interruption)"},
    "adv_checkpoint_help": {"zh": "每个阶段后保存进度；中断后可从上次进度继续。", "en": "Saves progress after each phase. If interrupted, you can resume from where you left off."},
    "gen_button": {"zh": "✦ 生成论文", "en": "✦  Generate Paper"},
    "gen_starting": {"zh": "正在启动…", "en": "Starting pipeline…"},
    # ─── Results ───
    "done": {"zh": "完成", "en": "Done"},
    "done_early": {"zh": "提前结束（质量达标）", "en": "terminated early (high quality)"},
    "done_rounds": {"zh": "共完成 {n} 轮迭代", "en": "completed in {n} rounds"},
    "resumed": {"zh": "已从上次断点恢复", "en": "Resumed from previous checkpoint"},
    "tab_draft": {"zh": "  草稿  ", "en": "  Draft  "},
    "tab_refs": {"zh": "  参考文献  ", "en": "  References  "},
    "tab_history": {"zh": "  迭代记录  ", "en": "  Iteration History  "},
    "tab_usage": {"zh": "  API 用量  ", "en": "  API Usage  "},
    "final_paper": {"zh": "## 最终论文", "en": "## Final Paper"},
    "no_draft": {"zh": "尚未生成草稿", "en": "No draft generated"},
    "refs_title": {"zh": "## 参考文献", "en": "## References"},
    "refs_heading_md": {"zh": "## 参考文献", "en": "## References"},
    "rounds_title": {"zh": "## 迭代轮次", "en": "## Iteration Rounds"},
    "usage_title": {"zh": "## API 用量统计", "en": "## API Usage Metrics"},
    "m_total_calls": {"zh": "总调用", "en": "Total Calls"},
    "m_success_rate": {"zh": "成功率", "en": "Success Rate"},
    "m_total_tokens": {"zh": "总 Token", "en": "Total Tokens"},
    "m_duration": {"zh": "总耗时", "en": "Duration"},
    "token_breakdown": {"zh": "### Token 分布", "en": "### Token Breakdown"},
    "m_in_tokens": {"zh": "输入 Token", "en": "Input Tokens"},
    "m_out_tokens": {"zh": "输出 Token", "en": "Output Tokens"},
    "usage_by_agent": {"zh": "### 按智能体统计", "en": "### Usage by Agent"},
    "agent_usage_line": {"zh": "**{agent}**：{calls} 次调用，{tokens} Token",
                         "en": "**{agent}**: {calls} calls, {tokens} tokens"},
    "errors_title": {"zh": "### 错误", "en": "### Errors"},
    # ─── Round cards ───
    "round_label": {"zh": "第 {n} 轮", "en": "Round {n}"},
    "phase_search": {"zh": "文献检索", "en": "Literature Search"},
    "phase_write": {"zh": "草稿生成", "en": "Draft Generation"},
    "phase_review": {"zh": "同行评审", "en": "Peer Review"},
    "phase_edit": {"zh": "编辑修订", "en": "Editorial Revision"},
    "generated_draft": {"zh": "### 生成的草稿", "en": "### Generated Draft"},
    "overall_score": {"zh": "综合评分", "en": "Overall Score"},
    "citation_accuracy": {"zh": "引用准确性", "en": "Citation Accuracy"},
    "quality_score": {"zh": "质量评分：{score}/10", "en": "Quality score: {score}/10"},
    "hallucination": {"zh": "**检测到幻觉引用：** {flags}", "en": "**Hallucination detected:** {flags}"},
    "strengths": {"zh": "优点", "en": "Strengths"},
    "improvements": {"zh": "待改进", "en": "Areas for Improvement"},
    "suggestions": {"zh": "修改建议", "en": "Suggestions"},
    "reviewer_summary": {"zh": "**评审小结：** {summary}", "en": "**Reviewer's Summary:** {summary}"},
    "changes_applied": {"zh": "已应用修改：{changes}", "en": "Changes applied: {changes}"},
    "no_changes": {"zh": "无需进一步修改", "en": "No further changes needed"},
    "revised_draft": {"zh": "修订后草稿", "en": "Revised Draft"},
    "unresolved": {"zh": "未解决：{items}", "en": "Unresolved: {items}"},
    "error_prefix": {"zh": "错误：{e}", "en": "Error: {e}"},
    # ─── How it works ───
    "how_title": {"zh": "使用方式", "en": "How it works"},
    "how_1": {"zh": "<strong>输入</strong>研究主题 —— 中文、英文都可以", "en": "<strong>Enter</strong> a research topic — Chinese or English, your choice"},
    "how_2": {"zh": "<strong>点击</strong>生成论文 —— 管线自动检索文献、写作并评审", "en": "<strong>Click</strong> Generate Paper — the pipeline searches literature, writes, and reviews automatically"},
    "how_3": {"zh": "<strong>下载</strong> Markdown、Word 或 PDF —— 每条引用都与源文献核验过", "en": "<strong>Download</strong> as Markdown, Word, or PDF — all citations are verified against source papers"},
    "how_shield": {"zh": "防幻觉：每条引用都会与检索到的文献图谱逐一核验。", "en": "Anti-hallucination: every citation is validated against the retrieved paper map."},
    # ─── Settings ───
    "set_title": {"zh": "设置", "en": "Settings"},
    "set_sub": {"zh": "配置 API 凭据，并单独测试管线各组件。", "en": "Configure API credentials and test pipeline components."},
    "tab_api": {"zh": "  API 配置  ", "en": "  API Configuration  "},
    "tab_debug": {"zh": "  调试台  ", "en": "  Debug Console  "},
    "api_card_title": {"zh": "API 配置", "en": "API Configuration"},
    "cloud_ok": {"zh": "API 密钥通过环境变量配置（云端部署），修改需在平台设置中进行。",
                 "en": "API key is configured via environment variables (cloud deployment). Changes must be made through platform settings."},
    "local_caption": {"zh": "凭据保存到 `.env` 并立即生效。切勿把 `.env` 提交到版本控制。",
                      "en": "Credentials are saved to `.env` and take effect immediately. Never commit `.env` to version control."},
    "env_readonly": {"zh": "环境变量为只读，如需修改请联系管理员。", "en": "Environment variables are read-only. Contact your administrator to change them."},
    "save_env": {"zh": "保存到 .env", "en": "Save to .env"},
    "help_env_var": {"zh": "通过环境变量设置", "en": "Set via environment variable"},
    "help_base_url": {"zh": "Anthropic 兼容接口地址", "en": "Anthropic-compatible endpoint"},
    "help_model": {"zh": "默认：MiniMax-M2.7-highspeed", "en": "Default: MiniMax-M2.7-highspeed"},
    "ss_optional": {"zh": "SEMANTICSCHOLAR_API_KEY（可选）", "en": "SEMANTICSCHOLAR_API_KEY (optional)"},
    "current_config": {"zh": "### 当前配置", "en": "### Current Configuration"},
    "api_key_label": {"zh": "API 密钥", "en": "API Key"},
    "base_url_label": {"zh": "接口地址", "en": "Base URL"},
    "model_label": {"zh": "模型", "en": "Model"},
    "ss_key_label": {"zh": "SS 密钥", "en": "SS Key"},
    "not_set": {"zh": "未设置", "en": "not set"},
    # ─── Debug console ───
    "dbg_title": {"zh": "调试台", "en": "Debug Console"},
    "dbg_caption": {"zh": "在运行完整管线前，单独测试各组件。", "en": "Test pipeline components independently before running the full pipeline."},
    "test1_title": {"zh": "测试 1 — 文献检索", "en": "Test 1 — Literature Search"},
    "search_query_ph": {"zh": "检索词", "en": "Search query"},
    "run": {"zh": "运行", "en": "Run"},
    "searching": {"zh": "检索中…", "en": "Searching…"},
    "search_failed": {"zh": "检索失败：{e}", "en": "Search failed: {e}"},
    "papers_found": {"zh": "找到 {n} 篇文献", "en": "{n} papers found"},
    "test2_title": {"zh": "测试 2 — LLM 接口调用", "en": "Test 2 — LLM API Call"},
    "test_prompt_label": {"zh": "测试提示词", "en": "Test prompt"},
    "call": {"zh": "调用", "en": "Call"},
    "calling": {"zh": "调用中…", "en": "Calling API…"},
    "api_ok": {"zh": "API 调用成功", "en": "API call succeeded"},
    "api_failed": {"zh": "API 调用失败：{e}", "en": "API call failed: {e}"},
    "response_label": {"zh": "**回复：** {resp}", "en": "**Response:** {resp}"},
    "test3_title": {"zh": "测试 3 — 管线试运行（检索＋写作）", "en": "Test 3 — Pipeline Dry Run (Search + Write)"},
    "test_topic_label": {"zh": "测试主题", "en": "Test topic"},
    "dry_run": {"zh": "试运行", "en": "Dry Run"},
    "dry_running_msg": {"zh": "管线运行中（约 30 秒），请稍候…", "en": "Pipeline running (~30s) — please wait…"},
    "dry_no_papers": {"zh": "没有找到文献", "en": "No papers found"},
    "dry_succeeded": {"zh": "试运行成功 —— 共处理 {n} 篇文献", "en": "Dry run succeeded — {n} papers processed"},
    "dry_outline": {"zh": "### 提纲", "en": "### Outline"},
    "dry_intro": {"zh": "### 引言（预览）", "en": "### Introduction (preview)"},
    "dry_failed": {"zh": "试运行失败：{e}", "en": "Dry run failed: {e}"},
    "unknown_error": {"zh": "未知错误", "en": "Unknown error"},
}

# Pipeline progress / error strings (thread-safe, explicit lang).
PROGRESS: dict[str, dict[str, str]] = {
    "prog_searching": {"zh": "正在检索 Semantic Scholar 与 PubMed…", "en": "Searching Semantic Scholar and PubMed..."},
    "prog_seeds": {"zh": "正在使用导入的 {n} 篇种子文献…", "en": "Using {n} imported seed papers..."},
    "prog_resuming": {"zh": "正在从断点恢复…", "en": "Resuming from checkpoint..."},
    "prog_writing": {"zh": "正在生成提纲、引言与相关工作…", "en": "Generating outline, introduction and related work..."},
    "prog_review": {"zh": "正在评审草稿（第 {r}/{n} 轮）…", "en": "Reviewing draft (round {r}/{n})..."},
    "prog_edit": {"zh": "正在编辑改进（第 {r}/{n} 轮）…", "en": "Editing and improving (round {r}/{n})..."},
    "prog_finalize": {"zh": "正在整理参考文献并收尾…", "en": "Formatting references and finalizing..."},
    "note_found": {"zh": "找到 {n} 篇文献", "en": "Found {n} papers"},
    "note_seeds": {"zh": "已导入研究助手的 {n} 篇收藏作为种子文献", "en": "Imported {n} seed papers from research-assistant favorites"},
    "err_no_papers": {"zh": "没有找到该主题的文献，换个关键词试试。", "en": "No papers found for this topic. Try different keywords."},
    "err_research": {"zh": "检索阶段失败：{e}", "en": "Research failed: {e}"},
    "err_writer": {"zh": "写作阶段失败：{e}", "en": "Writer failed: {e}"},
}


def get_lang() -> str:
    """Current UI language from session state (defaults to zh)."""
    lang = st.session_state.get("lang") or DEFAULT_LANG
    return lang if lang in LANGS else DEFAULT_LANG


def t(key: str, **fmt) -> str:
    """Translate a UI string key for the current session language."""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(get_lang()) or entry.get("en") or key
    return text.format(**fmt) if fmt else text


def pm(key: str, lang: str, **fmt) -> str:
    """Translate a pipeline progress/error string for an explicit language."""
    entry = PROGRESS.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get("en") or key
    return text.format(**fmt) if fmt else text


def render_lang_toggle() -> None:
    """
    Fixed top-right 中文 / EN switch (like a theme toggle).
    The widget key IS the language state ("lang" in session state);
    _init_state() seeds it with the default before first render.
    """
    st.segmented_control(
        "Language",
        options=list(LANGS),
        format_func=lambda v: "中文" if v == "zh" else "EN",
        key="lang",
        label_visibility="collapsed",
    )
