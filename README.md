# 智能问答本地调试

在项目根目录运行：

```powershell
uv sync
uv run langgraph dev --port 2025 --no-reload
```


## Agent Chat UI

保持上述 Agent Server 运行，在另一个终端执行：

```powershell
cd agent-chat-ui
pnpm dev
```
