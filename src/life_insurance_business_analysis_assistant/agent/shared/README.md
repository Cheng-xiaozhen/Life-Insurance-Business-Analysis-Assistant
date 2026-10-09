# 共用分析能力

## 职责

本目录提供跨图契约、步骤执行、图表和消息工具，不控制业务路由。调用方决定何时提交结果、推进索引及发布章节。

| 文件 | 内容 |
| --- | --- |
| [contracts.py](contracts.py) | 执行模板、步骤、数据记录、结论、图表及共用状态类型 |
| [execution.py](execution.py) | 步骤校验、请求构造、查询复用、结论生成和完成校验 |
| [charts.py](charts.py) | 基于已有数据生成并校验图表建议，组装渲染数据 |
| [messages.py](messages.py) | 固定消息 ID、问答正文流和消息构造 |

查询接口及响应校验由 [data_service/data_query.py](../../data_service/data_query.py) 负责，边界说明见 [数据服务](../../data_service/README.md)。

## 步骤与证据规则

- `ExecutionTemplate` 是本轮模板快照；`ScenarioStep` 描述步骤和指标，报告另带章节、指导及 `source_step_ids`。
- 每个有指标步骤一次查询可返回多张表，按 `step:{step_id}:table:{序号}` 保存来源步骤、请求快照和校验后的数据。请求相同且重验通过才复用；整批响应通过校验后才提交，不能保存部分失败响应。
- 有指标步骤只使用本步数据；无指标步骤使用前序结论及其去重后的数据引用，若设置 `source_step_ids` 则进一步限定范围，不允许引用尚未完成的步骤。引用已完成综合步骤时沿用其已校验的数据引用，保留原取数来源；生成前按原请求重验整批数据。
- `StepResult` 保存步骤编号、数据集引用和完整结论。拒绝空结论、工具调用及被截断的模型输出；前序步骤必须完整且顺序正确。
- `validate_references` 在生成、完成、场景总结、图表和报告组装时统一校验证据范围：有指标步骤仅引用本步数据，无指标步骤仅引用允许的前序结果已经引用的数据。`finalize_execution` 另检查全部步骤完成；查询或生成失败向外抛出，由业务图停止执行。

综合步骤的 `dataset_ids` 不创建新数据集或改写来源；图表按数据集去重并归属原取数步骤，报告在引用章节展示表格，同一章节内去重。

## 图表与消息规则

- 图表建议只使用实际分析引用的数据，每张图只引用一个已有数据集，不取新数、不隐式拼接或聚合。模型给出决策，代码校验来源、字段、图型条件并组装数值和单位。
- 当前图型为 `bar`、`line`、`pie`、`scatter`。无候选数据时不调用推荐模型；数据不适合图型时保留不推荐原因，未知引用等契约错误仍抛出。
- `analysis_progress` 表示执行状态；问答 `analysis_delta` 使用固定消息 ID 推送增量，完整状态消息替换临时展示。报告专用事件由 [报告模块](../subgraphs/report_generation/README.md) 管理。
- 消息 ID 为本轮分析 ID 加后缀；消息使用 `add_messages` 合并，`execution` 按键合并，避免重放产生重复记录。

`messages.py` 仅从模型协议的正文流提取文本；不收集或发送内部推理，也不将推理写入展示消息。所有模型调用（含独立分析图）使用 `TAG_NOSTREAM` 阻断原生 `messages` 模型事件，最终消息由已校验正文和业务元数据构造。图表流只显示操作状态，结构化 JSON 在校验完成后交付；报告使用相同正文边界。前端不再拼接推理增量，也不展示历史消息中的推理字段；已有检查点不在本次修改中迁移。

## 验证入口

项目根目录按涉及能力执行：

```powershell
.venv/Scripts/python.exe -B tests/test_data_query.py
.venv/Scripts/python.exe -B tests/test_analysis_execution.py
.venv/Scripts/python.exe -B tests/test_report_workflow.py
```

共用逻辑修改需检查问答和报告两侧影响，重点是引用范围、数据复用、失败不提交及图表来源。
