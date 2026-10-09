# 数据服务

## 职责

[data_query.py](data_query.py) 定义查询契约和校验，[mock_query_service.py](mock_query_service.py) 提供模型驱动的模拟查询。业务图通过 `AgentContext.query_data` 注入查询实现，不直接访问数据库。

## 关键规则

- 请求必须包含当前场景或报告模板基本信息、当前步骤描述和非空指标列表。请求上下文由问答或报告模块构造。
- 查询失败抛出 `DataQueryError`，不能伪装为空数据。
- 模拟查询使用 [prompts](../prompts/README.md) 中的 `mock_query` 提示词生成结构化数据；结构校验失败可纠正后重试一次，不为真实查询失败提供模拟回退。
- 接入真实服务时替换查询实现，保留契约校验，并明确真实接口的参数要求。数据复用和步骤证据规则见 [shared](../agent/shared/README.md)。


