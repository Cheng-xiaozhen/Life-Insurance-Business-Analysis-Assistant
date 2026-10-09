# 模板存储

## 职责

[scenario_store.py](scenario_store.py) 管理场景模板，[report_store.py](report_store.py) 管理报告模板。负责 YAML 读写和结构校验，不执行分析步骤。

模板资源仍位于项目根目录的 [Scenario](../../../config/templates/Scenario/) 和 [Report](../../../config/templates/Report/)；格式说明见 [模板说明](../../../docs/模板说明.md)。

## 调用与规则

- Python 调用方使用本模块的绝对导入。Next.js 的 `/api/scenarios` 和 `/api/report-templates` 直接启动对应脚本，传入模板目录，通过标准输入输出交换 JSON，不经过分析图。
- 两个脚本支持 `list` 和 `save`。移动脚本时须同步前端路径；目录由调用方传入，不依赖脚本所在位置。
- 保存前校验编码、字段和重名，拒绝符号链接及系统保留文件名；使用目录锁和临时文件替换，重命名失败时撤回新文件，最后清理临时文件和锁。
- 分析流程加载后使用本轮模板快照。章节展开与引用范围见 [报告模块](../agent/subgraphs/report_generation/README.md)，场景执行见 [问答模块](../agent/subgraphs/question_answer/README.md)。
