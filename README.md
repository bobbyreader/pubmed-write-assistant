# pubmed-write-assistant

AI 科研论文生成系统：输入研究主题，多 Agent 流水线（Researcher → Writer → Reviewer → Editor）自动检索真实文献、生成符合医学期刊 IMRaD 格式的论文草稿，并通过 citation_map 机制核验引文、防止幻觉引用。

- **线上站点**：https://pubmed-write-assistant.onrender.com
- **应用代码与完整说明**：见 [`ai-paper-tool/`](ai-paper-tool/README.md)
- **设计文档**：[`DESIGN.md`](DESIGN.md) / [`AI科研论文生成系统（优化落地版）V2.0.md`](AI科研论文生成系统（优化落地版）V2.0.md)

## 访问保护

公开部署请在平台环境变量中设置 `APP_PASSWORD`，设置后打开站点需先输入口令；不设置则为开放访问（页面侧边栏会给出警告）。
