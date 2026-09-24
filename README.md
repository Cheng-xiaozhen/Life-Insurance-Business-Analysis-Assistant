# 智能问答本地调试

在项目根目录运行：

```powershell
uv sync
uv run langgraph dev --port 5518 --no-reload
```

请求的服务地址为 `http://127.0.0.1:5518`，实际地址以终端输出的 `API` 为准。打开终端输出的 Studio 链接，
选择 `agent`，使用 Graph mode。

Windows 的保留端口可能导致指定端口无法绑定（即使没有进程监听），LangGraph 会自动换用其他端口。
可用 `netsh interface ipv4 show excludedportrange protocol=tcp` 查看保留范围。
若 Chat UI 报 `Failed to fetch`，先确认其 Deployment URL 与终端的 `API` 地址一致，
并打开该地址下的 `/info` 检查是否返回 JSON。

`langgraph.json` 自动加载根目录 `.env`。`LANGSMITH_API_KEY` 用于 LangSmith，
分析节点仍需 `DEEPSEEK_API_KEY` 及项目现有模型配置。
如需上传调用轨迹，设置 `LANGSMITH_TRACING=true`；只在本地调试可设为 `false`。

新建 Thread，输入以下 JSON：

```json
{"question": "分析2026年8月个险全系统的标保情况"}
```

也可以输入“分析标保和价值”，先在 interrupt 中以字符串
`standard_premium_review` 或 `value_review` 选择候选场景，再以字符串
`2026年8月个险全系统` 补参。恢复时使用 interrupt 的 Resume 操作，不要作为新问题提交。

此入口使用真实 LLM 和现有 Fake 查询，仅支持 **2026年8月、个险、全系统**。
查询范围直接取模板元数据：`渠道类型` → `渠道`，`分析对象` → `机构范围`；
当前传入值为 `个险`、`机构`，Fake 对应全系统模拟机构集合。用户只需补充年份、月份。
数据参考报告示例，机构明细包含模拟值，不代表该月真实经营数据。
每次新分析自动初始化 State；暂停恢复保留原 State。
检查点由 Agent Server 管理，不接入业务 FastAPI/SSE。

## Agent Chat UI

保持上述 Agent Server 运行，在另一个终端执行：

```powershell
cd agent-chat-ui
pnpm dev
```

打开 `http://localhost:3000`，Deployment URL 填终端输出的 API 地址（例如 `http://127.0.0.1:5518`），
Assistant / Graph ID 填 `agent`。使用终端实际输出的端口；
修改 Python 代码后，若使用 `--no-reload`，需要重启 Agent Server。

直接输入“分析2026年8月个险全系统的标保情况”。页面依次显示各步骤结论、
场景总结、图表推荐及图表。图表附带单位、数据限制和可展开的数据表。
匹配到一个或多个场景均需点击按钮确认；缺少参数时，在输入框补充明确的年份、月份、渠道及机构范围。
步骤含义需要澄清时，同样在输入框回复。
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

## 工作流与数据契约（第三阶段）

### 报告模板管理

打开 `/report-templates` 可加载、新增和编辑报告模板，文件保存在
`config/templates/Report/<报告编码>.yaml`。仅支持新格式：基本信息、章节板块（含子板块及分析步骤）、写作风格与格式要求，均使用中文字段名；步骤序号按列表顺序从 1 生成。
报告编码以字母或数字开头，仅含字母、数字、下划线和连字符，最长 100 字符，不能使用系统保留文件名。
修改编码会重命名文件；重复编码不会覆盖已有模板。保存失败保留页面中的编辑内容。
Next 通过项目 `.venv` 中的 Python 读写 YAML，可用 `REPORT_PYTHON` 和 `REPORT_TEMPLATE_DIR` 覆盖 Python 路径和目录。
页面不再读取或自动迁移浏览器中的旧模拟数据。目录中的旧格式文件需手动删除后加载。
启动 Next 后，在 `agent-chat-ui` 运行 `node scripts/check-report-templates.mjs` 验证，测试仅写临时目录。

### 场景模板管理

打开 `/scenarios` 可加载、新增和编辑模板。每个场景保存在
`config/templates/Scenario/<场景编码>.yaml`，使用中文字段名；分析思路包含步骤序号、
分析步骤、指标列表和可选分析模式。编码仅允许字母、数字、下划线和连字符，修改编码会重命名文件。
场景模板已删除输入参数声明；步骤取数参数会保留，取数流程将在后续调整。保存使用临时文件替换，失败时页面保留编辑内容。

Next 服务通过项目 `.venv` 中的 Python 和现有 PyYAML 读写文件，无需启动模型服务。
非默认环境可设置服务端 `SCENARIO_PYTHON`；`SCENARIO_TEMPLATE_DIR` 可覆盖管理页面的模板目录（默认与 Agent 共用上述目录）。
页面不再读取浏览器中的旧模拟数据。Agent 初始化时加载场景目录，匹配节点复用该目录；目录信息更新后需重启 Agent。已开始的分析仍使用其模板快照。
离线读写及页面回归：启动 Next 后，在 `agent-chat-ui` 运行 `node scripts/check-scenarios.mjs`，测试仅写临时目录。

`match_scenario → clarify → load_template → plan_step → fetch_step_data → analyze_step`
按模板顺序循环，最后 `summarize_scenario → recommend_charts`；聊天入口另有消息初始化、追问展示和最终图表消息节点。
已移除槽位填充节点；Planner 需要步骤澄清时经 `clarify` 恢复到 `plan_step`。
无需新数据时跳过取数；多份缺口查询每次只执行一份，各自保存检查点。
图表推荐与数值数据组装在同一节点完成，前端使用消息中的 `additional_kwargs.charts` 展示历史图表。

Planner 使用结构化 LLM 输出识别自然语言步骤的指标、粒度、相对月份、筛选和前序结论引用。
Python 校验指标目录、槽位绑定、时间范围、筛选范围、数据完整性和来源快照，并计算复用与补查。
业务模板无需增加执行策略；已有指标和取数参数仍有效，无数据步骤可使用空指标列表并引用前序结论。
`datasets` 保存数据一次，步骤结果保存引用和结论；当前步骤的 `step_plan` 在分析成功后清空。
取数逻辑暂时保留原实现，仍依赖明确的查询年月；新的参数来源将在后续调整。

取数函数现接收 `QueryRequest`，返回 `DatasetRecord`，不再接收旧的 `(metrics, params)`。
真实问数 API 接入时，在 `AgentContext` 同时注入 `query_data` 和 `query_capabilities`：

- `QueryCapabilities` 声明指标口径（月度/年累计）、单位、可用粒度及实体键。
- `DatasetRecord` 必须提供实际覆盖范围、来源、快照、完整性、截断标记、单位及 `data.rows`，不能照抄请求来宣称满足范围。
- `source_version` 表示可复现的数据快照，不是接口版本；无法保证稳定快照时填 `None`，Python 不跨数据集补查拼接。
- 全量需求不接受截断或缺失指标的响应；完整空结果允许，但不代表查询失败。查询异常直接抛出。
- 只在同一来源、快照、总体、粒度、时间和范围下复用；范围按精确匹配处理，可对完整数据应用显式筛选，不推断机构上下级关系或做隐式聚合。

当前仍只有项目原有报告样例适配器，没有真实问数 API；样例不能用于其他月份、渠道或范围。
百分数转换仅供绘图（例如 `61.8%` 转为 `61.8`，单位 `%`）。
折线图需要数据源显式声明 `time_dimensions` 和 ISO 日期；饼图需要 `partition_of` 声明真实整体份额。
Word 导出保持现有文字报告能力，暂不嵌入图表图片。

恢复必须使用同一个 `thread_id`：追问用 `Command(resume=...)`，失败重试用空输入 `None`。
已成功保存的查询和步骤不会重跑；若外部服务已响应但进程在检查点保存前退出，请求仍可能重发，生产适配器应使用 `request_key` 做幂等/去重。
仅支持当前状态结构和单场景 YAML 文件，不提供旧模板或旧检查点迁移；结构不兼容的历史分析需新建会话。
普通 Python 图默认 `InMemorySaver`；部署入口依赖 Agent Server 检查点，持久化需由部署环境提供。

本阶段基础验证（离线模型替身及明确样例，不验证真实模型语义）：

```powershell
uv run python -B tests/test_data_coverage.py
uv run python -B tests/test_plan_step.py
uv run python -B tests/test_analysis_loop.py
uv run python -B tests/test_graph.py
uv run python -B tests/test_chat.py
uv run python -B tests/test_workflow_integration.py
uv run python -B tests/test_prompt_contracts.py
cd agent-chat-ui
pnpm exec tsc --noEmit --incremental false
node scripts/check-analysis-interrupt.mjs
node scripts/check-analysis-charts.mjs
```

浏览器组件检查使用本机 Chrome 和已安装的 Playwright。
离线测试中标保五步只查询三次，价值三步只查询两次；实际次数取决于模型识别的需求及覆盖结果。
诊断时关注节点执行日志、`step_plan.reason`、查询 `request_key` 和检查点的待执行节点。
真实模型评估可手动运行 `tests/test_prompt_contracts.py --live --output <结果.json>`；会调用已配置模型并产生用量，需人工复核语义结果。
