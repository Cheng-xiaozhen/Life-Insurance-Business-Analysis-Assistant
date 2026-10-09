# 聊天入口与运行上下文

## 职责

入口父图只初始化本轮任务并分流，不管理业务步骤。子图分别维护 [智能问答](subgraphs/question_answer/README.md) 和 [报告生成](subgraphs/report_generation/README.md)，通过 [shared](shared/README.md) 复用能力，不直接调用彼此的节点。

| 文件 | 用途 |
| --- | --- |
| [graph.py](graph.py) | 创建父图，连接初始化节点与两个业务子图 |
| [nodes/prepare_request.py](nodes/prepare_request.py) | 校验输入，初始化问答或报告 |
| [state.py](state.py) | 外部输入 `StudioInput` 与父图状态 `ChatState` |
| [context.py](context.py) | 注入场景目录、模板路径和查询函数 |
| [studio.py](studio.py) | 加载本地模板及模拟查询服务，创建运行图 |
| [llm.py](llm.py) | 按思考模式创建并缓存模型实例 |

## 输入与路由

- 根目录 [langgraph.json](../../../langgraph.json) 将图 `agent` 指向 `studio.py:graph`，由 Agent Server 提供接口和检查点。
- `StudioInput` 接收 `question` 或新的用户 `messages`，以及可选的 `report_template_id`。只支持非空文本；同时提供问题和新消息时不能冲突，旧问题不能覆盖新消息。
- `prepare_request` 根据模板编码初始化任务：指定模板进入报告，显式 `null` 进入问答。同一线程省略该字段可能保留已选模板，切换模式须显式传值。
- 初始化后，父图根据 `report_id` 进入对应子图，子图完成后结束本轮。

## 状态与依赖

- `ChatState` 汇总问答状态和报告输出，不保存子图内部的步骤索引或待提交结果。每轮重置业务结果，保留线程消息历史，用 `analysis_id` 区分任务。
- 消息按 ID 合并，执行记录按记录键合并；业务字段通常覆盖更新，追加集合须返回合并后的完整值。
- `AgentContext` 保存服务端依赖，不写入业务 State。Chat UI 可传空上下文，聊天节点使用 `studio.py` 注入的配置；独立分析图的调用方仍须提供实际目录和查询配置。
- 每张图在自己的目录维护 `graph.py`、`state.py`、`nodes/` 和 `subgraphs/`。子模块规则由其 README 维护，不在父图重复。

