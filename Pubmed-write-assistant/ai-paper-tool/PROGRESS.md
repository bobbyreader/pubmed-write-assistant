# AI科研论文生成系统 — 项目进度

> 最后更新：2026-04-12 13:30

## 当前状态

**核心功能全部验证通过 ✅**

- Streamlit App 运行中：http://localhost:8501
- Test 1 (Search): ✅ PubMed fallback，3s返回
- Test 2 (LLM): ✅ MiniMax直调，thinking控制
- Test 3 (Pipeline): ✅ Outline + Introduction输出

---

## 已完成功能

### 1. SearchService — 学术论文搜索
- **语义 Scholar API** (primary)：直接 httpx 调用，支持 `SEMANTICSCHOLAR_API_KEY`（通过 `x-api-key` header 认证，突破 IP 级别限速）
- **PubMed E-utilities** (fallback)：429/错误时自动降级
- **timeout**: 15s 硬限制
- **文件**: `backend/services/search_service.py`

### 2. LLMService — MiniMax M2.7-highspeed 调用
- **直接 httpx** 调用，绕过 anthropic SDK 兼容性问题
- **thinking 控制**: `"thinking": {"type": "disabled"}`
- **max_tokens 默认 4096**：MiniMax 复杂任务生成超长 thinking，需足够 token budget
- **base_url**: `https://v2.aicodee.com` (aicodee 代理)
- **文件**: `backend/services/llm_service.py`

### 3. WriterAgent — 论文生成
- 多 Agent 架构：Researcher → Writer → Reviewer → Editor
- 反幻觉引用：只使用 citation_map 中的真实论文
- JSON 解析：处理 LLM 返回的 markdown fence 包装
- **文件**: `agents/writer.py`, `agents/base_agent.py`

### 4. Streamlit UI — 交互界面
- Test 1: 论文搜索
- Test 2: LLM API 调用
- Test 3: Mini Pipeline (Search + Write)
- Settings: API 配置页

---

## 技术架构

```
┌─────────────────────────────────────────────────┐
│                   Streamlit UI                    │
├─────────────────────────────────────────────────┤
│  Test 1 Search  │ Test 2 LLM  │ Test 3 Pipeline │
├─────────────────────────────────────────────────┤
│              WritingPipeline                       │
│  Researcher → Writer → Reviewer → Editor          │
├──────────────┬──────────────┬────────────────────┤
│ LLMService   │ RAGService  │ CitationService    │
│ (MiniMax)    │ (Context)   │ (Reference Mgmt)   │
├──────────────┴──────────────┴────────────────────┤
│     SearchService (SS primary + PubMed fallback)   │
└─────────────────────────────────────────────────┘
```

---

## 关键经验教训

### 1. semanticscholar 库 timeout 无效
**问题**: 库内部 httpx 调用有 10 次指数退避 retry，timeout 参数无法中断
**解法**: 移除库依赖，httpx 直调 API

### 2. dotenv 不覆盖 shell 环境变量
**问题**: `load_dotenv()` 默认不覆盖已存在的 `os.environ` 变量
**解法**: 全部改为 `load_dotenv(override=True)`

### 3. MiniMax thinking 吞 token
**问题**: `thinking: {"type": "disabled"}` 在复杂输入下仍生成超长 thinking
**解法**: `max_tokens` 设为 4096+，确保 text block 有足够空间

### 4. Streamlit 长任务 UI
**问题**: `st.spinner()` 内同步阻塞 → UI 无响应 → spinner 卡住
**解法**:
- 按钮点击 → `generating=True` + `st.rerun()`
- rerun 后 → 显示静态提示 + 同步执行 pipeline
- 执行完 → 写入 `dry_result` + `st.rerun()` 显示结果
- 关键：pipeline 执行块里**不能用 st.rerun()**，否则中断

### 5. WriterAgent JSON 解析失败
**问题**: LLM 返回 markdown 代码块（` ```json ... ``` `）包裹 JSON
**解法**: `parse_response()` 先去除 markdown fence 再 `json.loads()`

---

## 已知限制

- **Semantic Scholar API**: 免费 IP 限速 (429)，需 API key 或依赖 PubMed fallback
- **MiniMax thinking**: 复杂 prompt 生成超长 thinking，响应时间 30-40s
- **API Key**: `.env` 文件管理，需在 Settings 页面配置

---

## 启动方式

```bash
cd ai-paper-tool
streamlit run app.py --server.headless true --server.port 8501
```

---

## 下一步

- [x] ~~Add Semantic Scholar API Key 以提升搜索质量~~ ✅ (2026-04-12)
- [x] ~~Add full paper export (Word/PDF)~~ ✅ (2026-04-12)
  - **Word**: `python-docx`，支持标题层级、段落格式化
  - **PDF**: `reportlab`（纯 Python，无需系统依赖），支持 A4 排版、居中对齐
  - **导出服务**: `utils/export_service.py`
  - Markdown 下载按钮保留，三个格式并列


- [x] ~~Add real-time streaming progress feedback~~ ✅ (2026-04-12)
  - 后台线程执行 Pipeline，Queue 推送进度到主线程
  - st.rerun() 轮询消费 Queue，实时显示 phase icon + message + progress bar
  - Pipeline 各阶段（research → write → review → edit → finalize）都有进度更新

- [ ] 部署到云端
