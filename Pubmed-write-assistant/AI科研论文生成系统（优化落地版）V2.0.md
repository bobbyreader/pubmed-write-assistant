
### 项目关键约束（必须100%遵守）：
- LLM后端：MiniMax M2.7-highspeed（Anthropic-compatible API）
- 使用官方 `anthropic` Python SDK
- 必须通过 .env 配置：ANTHROPIC_API_KEY、ANTHROPIC_BASE_URL、ANTHROPIC_MODEL（默认 MiniMax-M2.7-highspeed）
- Semantic Scholar 使用 `semanticscholar` 库（>=0.12.0）
- RAG优先采用**全上下文注入**（10篇论文的abstract全部传入Writer）
- **严禁任何幻觉引用**：所有引用必须来自 citation_map，Writer/Reviewer/Editor必须严格检查
- Writer必须分步骤生成：大纲 → Introduction → Related Work
- 实现2-3轮 Reviewer + Editor 迭代优化
- 前端使用 Streamlit，必须清晰展示检索论文列表、多轮生成过程和Reviewer意见

### 项目结构（必须完全一致）：
```
ai-paper-tool/
├── agents/
│   ├── base_agent.py
│   ├── researcher.py
│   ├── writer.py
│   ├── reviewer.py
│   └── editor.py
├── backend/
│   └── services/
│       ├── llm_service.py          # MiniMax M2.7核心配置
│       ├── search_service.py
│       ├── citation_service.py
│       └── rag_service.py
├── workflows/
│   └── writing_pipeline.py
├── utils/
│   └── prompts.py                  # 所有prompt模板集中管理
├── app.py                          # Streamlit前端
├── .env.example
├── requirements.txt
└── README.md
```

### 输出规则（非常重要）：
请**严格按顺序**一步一步输出完整代码。每输出一步后停止，等待我确认后再继续下一步：

**Step 1**：requirements.txt + .env.example  
**Step 2**：utils/prompts.py + agents/base_agent.py + 全部Agent文件（researcher.py、writer.py、reviewer.py、editor.py）  
**Step 3**：backend/services/ 下全部服务文件（重点实现 llm_service.py）  
**Step 4**：workflows/writing_pipeline.py  
**Step 5**：app.py（完整Streamlit前端，包含侧边栏论文列表、多轮迭代Tab/Expander、下载功能）  
**Step 6**：README.md（包含项目介绍、安装配置、启动命令、测试Topic示例）

### 额外开发要求：
1. 所有Agent必须继承 BaseAgent，通过统一的 LLMService 调用模型。
2. Writer、Reviewer、Editor的system prompt中必须**强烈强化反幻觉**：
   - “你只能使用 citation_map 中已存在的引用编号，绝对禁止生成任何不在列表中的 [数字]。”
   - “如果缺少文献支持，必须说明‘需要更多文献’而非编造。”
3. Reviewer输出必须包含 score（1-10分），用于判断是否提前终止迭代。
4. Streamlit前端需要友好交互：侧边栏显示带[1][2]编号的论文卡片，主界面分轮次展示生成过程。
5. 代码需清晰、模块化，添加类型提示和必要注释。
6. 做好错误处理：API失败重试、检索为空时友好提示用户。

---

### 完整开发方案文档（请严格基于此文档开发）：

# 🧠 AI科研论文生成系统开发方案（优化落地版）

**项目名称**：AI-Paper-Tool（进阶版）  
**后端模型**：MiniMax M2.7-highspeed（通过 Anthropic-compatible API 中转调用）  
**目标**：构建一个严格反幻觉、可追溯引用、类人类分阶段写作的科研论文生成系统，支持 Semantic Scholar 真实文献检索 + 多轮审稿迭代。

## 🎯 核心原则（必须严格遵守）

### ❗ 1. 禁止伪造引用（最高优先级）
- 所有引用**必须**来自 Researcher Agent 的 Semantic Scholar 检索结果。
- 每个引用必须包含 `title`、`paperId`（或 DOI）。
- 严禁任何 Agent 编造论文或引用。

### ❗ 2. 引用机制
系统维护全局 `citation_map`：
```json
{
  "[1]": {
    "title": "Paper Title",
    "paperId": "S2_paper_id",
    "doi": "10.xxxx/xxxx",
    "year": 2025,
    "authors": ["Author1", "Author2"],
    "abstract": "...",
    "url": "https://..."
  }
}
```
- 生成内容时，每句引用用 `[1]`、`[2]` 标记。
- 最终论文必须包含 **References** 部分，格式为：
  ```
  [1] Author1, Author2. Title. Journal/Conference, Year. DOI: 10.xxxx
  ```

### 3. LLM 调用要求
- 使用 `anthropic` SDK + MiniMax Anthropic-compatible 接口。
- Model：`MiniMax-M2.7-highspeed`（默认）
- Base URL 通过 .env 配置。
- 所有 Agent 通过统一 `LLMService` 调用。
- prompts 中必须强化反幻觉指令。

## 🏗️ 项目结构（必须实现）
（与上方一致，省略重复）

## 🔍 Agent 设计

### 1. Researcher Agent
- 使用 `semanticscholar` 库调用 Semantic Scholar API。
- 输入：用户 topic（支持中英文）。
- 输出：最多10篇最相关论文 + 构建 `citation_map`。

### 2. Writer Agent（关键）
- 输入：topic、citation_map、全 abstract 上下文。
- 分步骤生成：大纲 → Introduction → Related Work。
- 每段至少1-2个有效引用，严格只使用 citation_map 中的编号。

### 3. Reviewer Agent
输出JSON结构：
```json
{
  "summary": "...",
  "score": 8,          // 1-10分
  "strengths": [...],
  "weaknesses": [...],
  "suggestions": [...]
}
```

### 4. Editor Agent
- 输入：当前draft + Reviewer意见
- 输出：修改后的版本，逐条修复建议，提升学术表达。

## 🔄 多轮写作流程
实现2-3轮迭代，如果Reviewer score ≥ 8.5 可提前结束。

## 🧠 RAG策略
优先全上下文注入（10篇abstract全部给Writer）。

## 🖥️ Streamlit 前端要求
- 侧边栏展示检索到的论文列表（带编号）
- 主界面分轮次/步骤展示生成过程
- 支持下载最终论文（Markdown）

## 📦 最终论文结构
Title + Introduction + Related Work + References

## ⚙️ 错误处理
API失败重试、空结果友好提示。

---

现在，请从 **Step 1** 开始：
输出 requirements.txt 和 .env.example 的**完整代码**。