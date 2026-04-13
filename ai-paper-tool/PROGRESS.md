# AI科研论文生成系统 — 项目进度

> 最后更新：2026-04-13

## 当前状态

**医学期刊格式验证通过 ✅ | Word/PDF 导出正常 ✅**

- Streamlit App 运行中：http://localhost:8501
- 搜索：PubMed fallback，SSL 已修复
- 流水线：Writer → Review(×3) → Editor，医学期刊格式
- 导出：Markdown ✅ Word ✅ PDF ✅

---

## 已完成功能

### 1. SearchService — 学术论文搜索
- **OpenAlex API** (primary)：free, no API key, full abstracts with inverted_index reconstruction
  - Valid select fields: id,doi,title,authorships,publication_year,abstract_inverted_index,primary_location,open_access
  - Filter syntax: `publication_year:YYYY-YYYY` (range) or `publication_year:>Y` / `publication_year:<Y`
- **Semantic Scholar API** (secondary)：补充搜索，提高引用多样性
  - fields: paperId,title,abstract,year,authors,venue,citationCount,externalIds,url
  - year filter: YYYY-YYYY range or YYYY- / -YYYY
- **PubMed E-utilities** (tertiary)：429/错误时自动降级，Google Translate 中文→英文
- **SSL 修复**：所有 httpx Client 使用 `certifi.where()` CA 证书，生产环境 MITM 防护已启用
- **搜索过滤器**：年份范围、作者、期刊名称、论文数量（5-50）
- **timeout**: 15s

### 2. LLMService — MiniMax M2.7 调用
- **timeout**: 180s（适应大输入 + 长输出）
- **thinking**: `"thinking": {"type": "disabled"}`
- `base_url`: `https://v2.aicodee.com/v1/messages`

### 3. RAGService — 上下文管理
- **摘要截断**：每篇摘要最大 800 字符，防止 token 溢出（2026-04-13 新增）
- **全量注入**：所有论文摘要注入 Writer/Reviewer/Editor 上下文

### 4. 医学期刊格式 (IMRaD)
- **Abstract**：结构化（BACKGROUND/OBJECTIVE/METHODS/RESULTS/CONCLUSION）
- **Introduction**：背景→研究空白→目标
- **Methods**：Study Design / Participants / Outcome Measures / Statistical Analysis
- **Results**：统计报告（effect size + 95% CI + p-values）
- **Discussion**：6 部分结构（Summary / Interpretation / Comparison / Limitations / Clinical Implications / Conclusion）
- **Conclusion**：150-250 词
- **引文格式**：Vancouver（方括号数字）
- **Related Work**：已移除（整合到 Introduction/Discussion）

### 5. 多 Agent 流水线
- Researcher → Writer → Reviewer(×3) → Editor
- Hallucination 检测：Reviewer 发现引用问题，Editor 修正
- Anti-hallucination 规则：禁止"相关数据"占位符，禁止引用错配

### 6. 导出服务
- **Word** (`export_word`): python-docx，含表格渲染
- **PDF** (`export_pdf`): reportlab + STHeiti 中文字体，含表格渲染
- **Markdown**: 原始文本下载

---

## 技术架构

```
┌─────────────────────────────────────────────────┐
│                   Streamlit UI                    │
├─────────────────────────────────────────────────┤
│  Generate Paper │ Search Filters │ Settings     │
├─────────────────────────────────────────────────┤
│              WritingPipeline                      │
│  Researcher → Writer → Reviewer(×3) → Editor    │
├──────────────┬──────────────┬──────────────────┤
│ LLMService   │ RAGService   │ CitationService  │
│ (MiniMax)    │ (Context)    │ (Reference Mgmt)│
├──────────────┴──────────────┴──────────────────┤
│  SearchService (OpenAlex + Semantic Scholar + PubMed) │
└─────────────────────────────────────────────────┘
```

---

## Agent max_tokens 配置

| Agent | max_tokens | 说明 |
|-------|-----------|------|
| Writer | 16384 | 6 大章节 + 50 篇摘要输入 |
| Reviewer | 12288 | 长草稿 + citation_map + abstracts（2026-04-13 升级自 8192） |
| Editor | 12288 | 长草稿 + reviewer feedback（2026-04-13 升级自 8192） |

---

## 关键经验教训

### 1. SSL EOF 导致 PubMed/SS 请求失败
**问题**: macOS 上 httpx 默认 SSL 验证对某些 API 证书失败，`EOF occurred in violation of protocol`
**解法**: 所有 `httpx.Client()` 添加 `verify=False`

### 2. MiniMax thinking 吞 token
**问题**: 复杂 prompt 生成超长 thinking，导致 JSON 截断
**解法**: max_tokens 逐步调高（Writer→16384，Reviewer/Editor→8192），timeout→180s

### 3. ReportLab RGBColor vs python-docx RGBColor
**问题**: 两个库都有 `RGBColor`，但参数范围不同（docx: 0-255, reportlab: 0-1）
**解法**: ReportLab table 用 `HexColor('#hexstr')`，不用 `RGBColor`

### 4. Medical journal JSON schema 遵循
**问题**: LLM 返回非预期 JSON 结构（嵌套对象、多余字段）
**解法**: OUTPUT FORMAT 前置 + 示例 + 字段类型约束

### 5. Streamlit 长任务 UI
**问题**: `st.spinner()` 同步阻塞
**解法**: 按钮 → `generating=True` + `st.rerun()` → 后台执行 → 结果写入 → `st.rerun()`

---

## 安全修复（2026-04-13）

- **R-1**: `verify=False` → `certifi.where()`，所有外部 API 调用启用 CA 证书验证
- **R-2**: Dockerfile `server.address` 从 `0.0.0.0` 改为 `127.0.0.1`，容器端口不对公网暴露
- **R-3**: `.env` 已纳入 `.gitignore`
- **R-4**: langchain 传递依赖冲突（未实际 import，不影响）
- **R-5**: Dockerfile Python 版本统一为 `3.9-slim`

## 已知限制

- **OpenAlex rate limits**: polite pool可用，短期内大量请求可能触发429（会fallback到PubMed）
- **Reviewer R3**: 草稿很大时可能 JSON 截断（8192 tokens 不够），但 R2 的 hallucination 反馈已能修正主要问题
- **论文内容**: 建议用户根据实际情况修改 Methods 部分（检索策略描述为 AI 生成，可能需按真实检索行为调整）

---

## 启动方式

```bash
cd ai-paper-tool
streamlit run app.py --server.headless true --server.port 8501
```

---

## 下一步

- [x] ~~医学期刊格式改进~~ ✅ (2026-04-12)
  - Structured Abstract (BACKGROUND/OBJECTIVE/METHODS/RESULTS/CONCLUSION)
  - Methods / Results / Discussion 6-part 结构
  - Vancouver 引用风格
- [x] ~~Search Filters~~ ✅ (2026-04-12)
  - 年份范围、作者、期刊名称、数量
- [x] ~~OpenAlex集成~~ ✅ (2026-04-13)
  - 替代被IP封锁的Semantic Scholar
  - 全字段抽象、作者、期刊元数据
  - 年份过滤器(范围/从/到)
- [x] ~~Word/PDF 导出修复~~ ✅ (2026-04-12)
  - 中文字体 (STHeiti)
  - 表格渲染
  - RGBColor 混用问题
- [ ] 部署到云端
