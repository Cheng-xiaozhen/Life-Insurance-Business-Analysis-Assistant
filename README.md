# 智能问答本地调试

在项目根目录运行：

```powershell
uv sync
uv run langgraph dev --port 2025--no-reload
```

服务默认地址为 `http://127.0.0.1:2025`。打开终端输出的 Studio 链接，
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

## Agent Chat UI

保持上述 Agent Server 运行，在另一个终端执行：

```powershell
cd agent-chat-ui
pnpm dev
```

打开 `http://localhost:3000`，Deployment URL 填 `http://127.0.0.1:2025`，
Assistant / Graph ID 填 `insurance_analysis`。使用终端实际输出的端口；
修改 Python 代码后，若使用 `--no-reload`，需要重启 Agent Server。

直接输入“分析2026年8月个险全系统的标保情况”。页面依次显示各步骤结论、
场景总结和图表推荐说明。图表推荐目前仅输出说明，不绘图。
遇到多个场景时点击场景按钮；缺少参数时，在输入框回复“2026年8月”等文本。
这些回复恢复当前分析，不会清空已经确认的槽位。

完成后可以在同一会话输入另一个完整问题：聊天记录保留，业务状态重新初始化。
暂不支持“换成上个月”等依赖前文的自由追问，也不支持图片/PDF 分析。
未适配的历史消息编辑与重新生成按钮在分析会话中隐藏。

页面刷新后，从 Agent Server 检查点恢复消息及待处理追问。
模型或取数失败时，修复连接/配置后点击“从失败处重试”，从失败节点继续。
流式半成品不会作为已完成业务结论保存。服务重启后的保存能力取决于开发服务自身存储，
不应将本地开发检查点当作生产持久化保证。

聊天 API 使用 `messages`；Studio 保留 `question` 输入。建议每次只提交一种输入；
Chat UI 会显式传 `question: null`，防止上一轮问题干扰新消息。
消息历史仅用于展示，业务 Prompt 仍只读取原问题、槽位和当前节点所需数据。

离线回归（不调用真实模型）：

```powershell
uv run python -B tests/test_chat.py
uv run python -B tests/test_workflow_integration.py
```
