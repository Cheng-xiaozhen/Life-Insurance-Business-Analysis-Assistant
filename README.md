# 智能问答本地调试

在项目根目录运行：

```powershell
uv sync
uv run langgraph dev --no-reload
```

服务默认地址为 `http://127.0.0.1:2024`。打开终端输出的 Studio 链接，
选择 `insurance_analysis`，使用 Graph mode。

`langgraph.json` 自动加载根目录 `.env`。`LANGSMITH_API_KEY` 用于 LangSmith，
分析节点仍需 `DEEPSEEK_API_KEY` 及项目现有模型配置。
如需上传调用轨迹，设置 `LANGSMITH_TRACING=true`；只在本地调试可设为 `false`。

新建 Thread，输入以下 JSON：

```json
{"question": "分析2026年8月个险全系统的标保情况"}
```

也可以输入“分析标保和价值”，先在 interrupt 中以字符串
`standard_premium_review` 或 `value_review` 选择候选场景，再以字符串
`2026年8月` 补参。恢复时使用 interrupt 的 Resume 操作，不要作为新问题提交。

此入口使用真实 LLM 和现有 Fake 查询，仅支持 **2026年8月、个险、全系统**。
数据参考报告示例，机构明细包含模拟值，不代表该月真实经营数据。
每次新分析自动初始化 State；暂停恢复保留原 State。
检查点由 Agent Server 管理，不接入业务 FastAPI/SSE。
