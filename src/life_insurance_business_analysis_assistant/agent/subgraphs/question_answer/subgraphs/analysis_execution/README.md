# 问答分析循环

## 职责与边界

本子图按模板逐步取数和分析，不负责场景选择、场景总结、报告章节或聊天消息。[graph.py](graph.py) 控制循环，[state.py](state.py) 定义边界，节点在 [nodes](nodes/)；步骤业务函数复用 [shared](../../../../shared/README.md)。

| 边界 | 内容 |
| --- | --- |
| 输入 `AnalysisExecutionInput` | 仅 `template` |
| 内部 `AnalysisExecutionState` | 模板、`step_index`、`current_step`、`datasets`、`step_results` |
| 输出 `AnalysisExecutionOutput` | 仅 `analysis_result = {datasets, step_results}` |

## 节点与循环

| 节点 | 职责 |
| --- | --- |
| `initialize_subgraph` | 检查模板非空，索引置 0，清空当前步骤、数据和结论 |
| `load_step` | 按索引读取并校验当前步骤 |
| `fetch_step_data` | 有指标时调用查询接口，响应全部校验通过后保存数据，不推进索引 |
| `analyze_step` | 根据允许证据生成完整结论，追加结果并将索引加 1 |
| `finalize_subgraph` | 校验所有步骤已完成、结果顺序及数据引用，输出唯一业务结果 |

`load_step` 后，有指标走查询节点，无指标直接分析；分析后有剩余步骤则回到加载，否则结束校验。非法索引报错。

## 关键规则

- `step_index` 从 0 开始，`step_id` 从 1 开始且连续。追加数据和结论时返回完整集合，不能用单条记录覆盖前序结果。
- 模板和业务依赖分开：模板是输入，查询函数从运行上下文获取；不接收原始问题，也不增加用户参数提取。
- 查询失败不写入部分响应，结论不完整不推进索引。子图继承父图检查点，不自行增加跳过或重排步骤的路线。
- 数据复用、证据选择和完成校验由 [shared](../../../../shared/README.md) 统一定义。无指标步骤读取允许范围内前序结论及其引用数据，不增加查询。

## 验证入口

项目根目录执行：

```powershell
.venv/Scripts/python.exe -B tests/test_analysis_execution.py
```

重点检查有／无指标分支、多表响应、查询复用、失败恢复、结果顺序及输入输出边界。此检查替换模型和查询服务，不代表真实模型分析质量通过。
