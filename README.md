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
场景模板不声明输入参数或步骤取数参数；指标为空的步骤直接分析。保存使用临时文件替换，失败时页面保留编辑内容。

Next 服务通过项目 `.venv` 中的 Python 和现有 PyYAML 读写文件，无需启动模型服务。
非默认环境可设置服务端 `SCENARIO_PYTHON`；`SCENARIO_TEMPLATE_DIR` 可覆盖管理页面的模板目录（默认与 Agent 共用上述目录）。
页面不再读取浏览器中的旧模拟数据。Agent 初始化时加载场景目录，匹配节点复用该目录；目录信息更新后需重启 Agent。已开始的分析仍使用其模板快照。
离线读写及页面回归：启动 Next 后，在 `agent-chat-ui` 运行 `node scripts/check-scenarios.mjs`，测试仅写临时目录。

`match_scenario → clarify → load_template → 按 metrics 路由 → fetch_step_data / analyze_step`

指标非空时每步调用一次 Query Service，然后分析；指标为空时直接分析前序结论。步骤完成后循环，最后执行 `summarize_scenario → recommend_charts`。不再执行查询规划、步骤澄清或跨步骤覆盖复用。

`AgentContext.query_data` 接收严格的 `DataQueryRequest`（scenario、step、metrics），返回 `DataQueryResult`（一张或多张结构化表）。slots、原始问题、推导条件不传入；当前接口不能保证按用户指定年月或机构查询，分析与总结不凭用户问题给数据补写口径。

Studio 默认注入 LLM `MockQueryService`，需要配置模型密钥。数值由 LLM 生成，Pydantic 校验结构，代码强制标明模拟来源。不同步骤为独立样例，不保证同一业务快照；没有硬编码数据回退。未来替换为 HTTP 适配器即可，Graph 不变。

数据按 `step:2:table:1` 保存，结论只保存 dataset_ids 和 conclusion_step_ids。图表继续使用已有数据，由 Python 组装数值；百分比使用数值和 `%` 单位。折线要求 time_dimensions，饼图要求 partition_of。Word 导出保持现有文字报告能力。

失败不推进步骤；多表验证成功后原子保存，分析失败不重复取数。同 thread_id 的确认使用 Command(resume=...)，失败恢复使用 None。服务响应后、检查点保存前退出仍可能重发请求，不保证 exactly-once。旧规划检查点不迁移，请开始新分析。

离线验证（不调用真实模型）：

```powershell
uv run python -B tests/test_data_query.py
uv run python -B tests/test_fetch_step_data.py
uv run python -B tests/test_analysis_loop.py
uv run python -B tests/test_graph.py
uv run python -B tests/test_chat.py
uv run python -B tests/test_workflow_integration.py
uv run python -B tests/test_prompt_contracts.py
```

当前标保五步查询五次，价值三步查询三次。诊断关注节点日志、dataset_id、保存的 request 和检查点待执行节点。
详细契约见 [系统架构设计说明](docs/系统架构设计说明.md)。真实模型评估可手动运行 `tests/test_prompt_contracts.py --live --output <结果.json>`，需人工复核语义质量。
