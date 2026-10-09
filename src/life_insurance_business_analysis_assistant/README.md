# AI Service

## 职责与导航

本包负责模板驱动的问答、报告生成和图表推荐。前端负责交互与渲染，数据访问通过查询接口注入。系统设计见 [ARCHITECTURE.md](../../docs/ARCHITECTURE.md)，产品目标见 [PRODUCT.md](../../docs/PRODUCT.md)。模块文档描述当前实现，未实现要求单独标注。

| 入口 | 职责 |
| --- | --- |
| [agent](agent/README.md) | 聊天入口、状态边界和依赖配置 |
| [智能问答](agent/subgraphs/question_answer/README.md) | 场景匹配、确认、分析和总结 |
| [报告生成](agent/subgraphs/report_generation/README.md) | 模板展开、章节生成与报告组装 |
| [共用能力](agent/shared/README.md) | 数据引用、步骤生成、图表和消息规则 |
| [data_service](data_service/README.md) | 查询契约、响应校验和模拟取数 |
| [templates](templates/README.md) | YAML 模板读写与校验 |
| [prompts](prompts/README.md) | 提示词文件与加载 |
| [settings.py](settings.py) | 包级配置 |

各功能目录维护自己的实现规则。注意`templates/` 存放模板管理代码，项目根目录 `config/templates/` 存放 模板YAML文件，两者分开。