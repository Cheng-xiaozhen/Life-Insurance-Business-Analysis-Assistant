# 寿险经营分析助手

基于 LangGraph 的寿险经营分析助手，支持模板驱动的智能问答、月度报告生成、执行过程流式展示和图表推荐。仓库包含 Python AI Service 和 Next.js 前端，可在本机启动后通过浏览器试用。

当前数据服务由模型生成模拟数据，尚未接入真实业务数据库。页面中的分析和模拟取数都需要可用的模型 API；离线回归测试使用测试替身，不需要 API Key。

## 1. 环境准备

| 工具 | 要求或用途 |
| --- | --- |
| Git | 克隆代码；也可下载并解压完整仓库 |
| Python | 3.11 或更高版本，见 `pyproject.toml` |
| uv | 安装 Python 依赖和运行后端命令 |
| Node.js | 20.9.0 或更高版本；本地验证环境为 Node.js 24 |
| pnpm | 使用 `agent-chat-ui/package.json` 声明的 **10.5.1** |
| 模型服务 | 页面试用需要 DeepSeek API Key、可访问的服务地址和有权限调用的模型 |

安装 Python 和 Node.js 后，可以用以下命令安装工具：

```shell
python -m pip install uv
npm install --global pnpm@10.5.1
```

检查工具是否可用：

```shell
python --version
uv --version
node --version
pnpm --version
```

首次安装依赖需要联网。以下命令除特别标注外，可用于 PowerShell 和 macOS/Linux 终端；带空格的目录路径请加引号。

## 2. 获取代码与安装依赖

```shell
git clone https://github.com/Cheng-xiaozhen/Life-Insurance-Business-Analysis-Assistant.git
cd Life-Insurance-Business-Analysis-Assistant
uv sync --frozen
cd agent-chat-ui
pnpm install --frozen-lockfile
cd ..
```

如果已经拿到完整源码，直接进入项目根目录，从 `uv sync --frozen` 开始执行。`--frozen` / `--frozen-lockfile` 使用仓库中的锁文件；不要只复制前端目录或只安装 Python 的生产依赖，后端启动命令来自默认安装的 `dev` 依赖组。

`uv sync` 会在根目录创建 `.venv`，无需手动激活。前端模板管理接口也会调用此 Python 环境，并读取根目录的 `config/templates/`，因此请保持仓库目录结构。

## 3. 配置环境变量

首次配置时复制示例文件；已有本地配置时直接编辑，避免覆盖。

Windows PowerShell（项目根目录）：

```powershell
Copy-Item .env.example .env
Copy-Item agent-chat-ui/.env.example agent-chat-ui/.env.local
```

macOS/Linux（项目根目录）：

```bash
cp .env.example .env
cp agent-chat-ui/.env.example agent-chat-ui/.env.local
```

### 后端：根目录 `.env`

```dotenv
DEEPSEEK_API_KEY=替换为你自己的API_KEY
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
BACKEND_BASE_URL=http://localhost:8080
```

`DEEPSEEK_MODEL` 沿用仓库示例值，请按自己的模型服务权限填写；使用兼容服务时，同时填写对应的 `DEEPSEEK_BASE_URL`。当前适配器使用 DeepSeek provider，并发送 `thinking` 参数，服务需要支持当前调用格式。API Key 只填写在后端 `.env` 中。

`BACKEND_BASE_URL` 是预留配置，当前启动入口直接注入模拟查询服务，不访问这个地址。**本地试用不需要另起 8080 服务、数据库或 Redis。**

### 前端：`agent-chat-ui/.env.local`

将对应配置改为：

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:2025
NEXT_PUBLIC_ASSISTANT_ID=agent
NEXT_PUBLIC_AUTH_SCHEME=
LANGSMITH_API_KEY=
```

注意：前端 `.env.example` 原值为 **2024**，本指南统一使用 **2025**，必须修改。`agent` 对应根目录 `langgraph.json` 中的图名称。本地直连无需 LangSmith API Key，也无需配置 `LANGGRAPH_API_URL`。

修改环境变量后重启对应服务。`.env` 和 `.env.local` 已被 Git 忽略，不随源码分享。

## 4. 启动项目

需要保持两个终端运行。

**终端一：在项目根目录启动 AI Service。**

```shell
uv run --frozen langgraph dev --port 2025 --no-reload --no-browser
```

启动后可访问：

- 健康检查：<http://localhost:2025/ok>
- API 文档：<http://localhost:2025/docs>

`--no-browser` 避免自动打开 Studio；`--no-reload` 禁用自动重载，修改后端代码后需重启。开发时可去掉 `--no-reload`。

**终端二：从项目根目录进入前端并启动。**

```shell
cd agent-chat-ui
pnpm dev --port 3000
```

浏览器打开 <http://localhost:3000>。若出现连接配置页，填写 Deployment URL 为 `http://localhost:2025`、Assistant/Graph ID 为 `agent`，API Key 留空，不启用 Agent Builder。

检查两个终端输出的实际监听端口。端口被占用时，开发服务可能自动选择其他端口；此时需同步修改前端 API 地址并重启前端，或先释放所需端口。

停止服务时，在各自终端按 `Ctrl+C`。再次启动只需执行本节两组命令；拉取代码后若依赖变化，再执行第 2 节的安装命令。

## 5. 验证本地运行

### 服务检查

另开终端执行。Windows PowerShell：

```powershell
Invoke-RestMethod http://localhost:2025/ok
Invoke-RestMethod http://localhost:2025/assistants/search -Method Post -ContentType 'application/json' -Body '{}'
Invoke-RestMethod http://localhost:3000/api/scenarios
Invoke-RestMethod http://localhost:3000/api/report-templates
```

macOS/Linux：

```bash
curl -fsS http://localhost:2025/ok
curl -fsS http://localhost:2025/assistants/search -H 'Content-Type: application/json' -d '{}'
curl -fsS http://localhost:3000/api/scenarios
curl -fsS http://localhost:3000/api/report-templates
```

预期：健康检查返回 `ok: true`；助手列表包含 `graph_id: agent`；两个模板接口分别返回场景和报告模板数据。健康检查通过只表示服务可访问，模型是否可用还需下面的页面试用验证。

### 页面试用（调用真实模型）

1. 智能问答：输入“请分析 2026 年 8 月个险全系统标保经营情况”，选择并确认“标保经营检视”候选场景。即使只有一个候选，也需确认后才开始分析。
2. 检查执行过程、逐步生成的结论、场景总结和最终图表或表格。图表按数据适用性推荐，不保证每一步都有图表。
3. 报告生成：选择“月度经营分析”模板，输入“请生成 2026 年 8 月个险全系统月度经营分析报告”，检查章节内容逐步填入，最终状态为完成。

以上结果使用模拟业务数据，只用于功能试用。若执行失败，请结合页面提示和后端终端日志定位失败步骤。

### 离线回归测试

只需先安装 Python 依赖，在项目根目录逐条执行；无需启动前后端，也无需配置模型 API Key：

```shell
uv run --frozen python -B tests/test_data_query.py
uv run --frozen python -B tests/test_analysis_execution.py
uv run --frozen python -B tests/test_report_workflow.py
uv run --frozen python -B tests/test_prior_data.py
```

这组测试覆盖查询契约、分析子图、报告流程、失败恢复和前序数据引用。以退出码为 0 且出现 `PASS` 为通过；报告测试中的“模拟故障”异常日志属于预期用例。这是基础回归集，并非全量测试。

已知限制：`tests/test_prompt_contracts.py` 仍有旧提示词契约断言未对齐，不能把基础回归通过视为全部测试通过，详情见 [会话交接](docs/session-handoff.md)。

### 前端类型检查和构建

在 `agent-chat-ui/` 目录执行：

```shell
pnpm exec tsc --noEmit
pnpm build
```

若要用构建产物在本地运行，先停止前端开发服务，再执行：

```shell
pnpm start --port 3000
```

此时仍需保持 AI Service 运行。修改 `NEXT_PUBLIC_*` 配置后需要重新构建。本指南提供本地开发和测试方式，`langgraph dev` 是开发服务，不代表生产部署方案。

## 6. 常见问题

| 现象 | 排查方式 |
| --- | --- |
| `uv`、`node` 或 `pnpm` 找不到 | 检查安装与 PATH，重新打开终端后运行版本检查命令 |
| Windows 安装依赖时报 `.pyd` 文件拒绝访问 | 停止使用本项目 `.venv` 的 Python 服务后重新执行 `uv sync --frozen` |
| 前端无法连接后端 | 先访问 `/ok`，核对后端实际端口、`.env.local` 和页面连接设置是否一致；本指南使用 2025 |
| 提示模型未配置、401 或模型不存在 | 检查根目录 `.env` 中的 Key、地址和模型权限，修改后重启后端 |
| 场景或报告文件服务不可用 | 在根目录完成 `uv sync --frozen`，并从 `agent-chat-ui/` 启动前端；确认 `.venv` 和 `config/templates/` 存在 |
| 修改配置后未生效 | 重启对应服务；构建模式下前端还需重新执行 `pnpm build` |
| pnpm 提示锁文件不匹配 | 先确认使用 10.5.1，并确保 `package.json` 与 `pnpm-lock.yaml` 来自同一版本代码 |

## 7. 目录与开发资料

| 路径 | 内容 |
| --- | --- |
| `agent-chat-ui/` | Next.js 页面、交互及模板管理接口 |
| `src/life_insurance_business_analysis_assistant/` | AI 分析流程、模型调用和数据查询契约 |
| `config/templates/Scenario/` | 场景 YAML 模板 |
| `config/templates/Report/` | 报告 YAML 模板 |
| `tests/` | 回归测试与测试夹具 |
| `langgraph.json` | Agent Server 图入口及环境文件配置 |

- [产品需求](docs/PRODUCT.md)
- [系统架构](docs/ARCHITECTURE.md)
- [AI Service 模块导航](src/life_insurance_business_analysis_assistant/README.md)
- [当前状态与已知限制](docs/session-handoff.md)
- [历史进展与验证记录](docs/PROGRESS.md)
