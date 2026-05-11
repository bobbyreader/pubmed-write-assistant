# AI Paper Tool - Claude 项目指南

## 项目概述

AI Paper Tool 是一个 AI 驱动的学术论文生成系统，基于真实引用（从 OpenAlex/Semantic Scholar/PubMed）生成结构化医学期刊格式论文，避免幻觉。

## 技术栈

- **前端**: Streamlit
- **LLM**: MiniMax M2.7 (通过 Anthropic 兼容 API)
- **搜索**: OpenAlex (主) + Semantic Scholar (次) + PubMed (降级)
- **导出**: python-docx (Word), reportlab (PDF)
- **测试**: pytest

## 项目结构

```
ai-paper-tool/
├── agents/              # Agent 类
│   ├── base_agent.py     # 抽象基类
│   ├── researcher.py     # 搜索论文 → citation_map
│   ├── writer.py         # 生成大纲 + 章节
│   ├── reviewer.py       # 评分批评 + 幻觉检测
│   └── editor.py         # 根据反馈修订
├── backend/services/
│   ├── llm_service.py     # MiniMax API 调用
│   ├── search_service.py # 学术搜索 API
│   ├── citation_service.py # 引用管理
│   ├── rag_service.py    # 上下文管理
│   ├── metrics_service.py # API 使用统计
│   └── checkpoint_service.py # 断点续传
├── workflows/
│   └── writing_pipeline.py # 主编排
├── utils/
│   ├── prompts.py        # 所有系统提示词
│   └── export_service.py # Word/PDF 导出
└── app.py               # Streamlit 前端
```

## 关键配置

- **max_tokens**: Writer=16384, Reviewer/Editor=12288
- **timeout**: LLM=180s, 搜索=15s
- **temperature**: Writer=0.6, Reviewer=0.3, Editor=0.4
- **MAX_ROUNDS**: 3 次 Review-Edit 迭代
- **早退条件**: score >= 8.5 AND citation_accuracy == 10

## 开发约定

### 1. Agent 命名
所有 Agent 在实例化时必须指定 `agent_name` 用于 metrics 追踪：
```python
AgentConfig(
    system_prompt=...,
    max_tokens=...,
    agent_name="writer",  # 必须
)
```

### 2. JSON 输出
- Writer/Reviewer/Editor 返回 JSON 格式
- 支持 markdown code fence 去除
- 支持截断 JSON 修复

### 3. SSL 证书
所有 httpx.Client 必须使用 certifi.where() 验证：
```python
httpx.Client(verify=certifi.where())
```

### 4. Metrics 追踪
- 所有 LLM 调用自动记录到 metrics/api_calls.jsonl
- 使用 MetricsService 单例获取统计数据

### 5. Checkpoint
- CheckpointService 保存进度到 checkpoints/ 目录
- 意外中断后可恢复

## 常见问题

### JSON 截断
Reviewer/Editor 的 12288 tokens 对大论文可能不够。如果出现截断：
1. 检查 abstract_context 是否过长（已限制 800 字符/篇）
2. 考虑分块处理或增加 max_tokens

### 搜索失败
三级降级：OpenAlex → Semantic Scholar → PubMed
如果全部失败，检查网络和 API 密钥。

### MiniMax thinking
已禁用 thinking 以避免 JSON 截断。

## 启动命令

```bash
cd ai-paper-tool
streamlit run app.py --server.headless true --server.port 8501
```

## 测试

```bash
cd ai-paper-tool
pytest tests/ -v
```

## 注意事项

- 不要在 prompts.py 中硬编码 API 密钥
- 不要在 git 中提交 .env 文件
- Reviewer 主要检测引文幻觉，不是语法检查
