# 提示词

## 职责

本目录保存模型提示词及 [prompt_loader.py](prompt_loader.py)。调用方通过 `load_prompt(name)` 加载同名 Markdown，例如 `load_prompt("analyze_step")`。

## 加载规则

- 使用 `importlib.resources` 读取当前包内资源，不依赖工作目录；发布包必须包含提示词文件。
- 名称须为合法标识符，不带路径或扩展名。按 UTF-8 读取，空提示词报错。
- 每次调用读取最新文件，不缓存、不插值，保留 JSON 和槽位中的花括号。`README.md` 是模块说明，不作为业务提示词调用。
- 提示词只能指导模型表达，不能替代代码中的数据校验、来源检查或工作流控制。业务约束见 [shared](../agent/shared/README.md)。

## 验证

修改加载器时检查全部业务提示词可读取、非法名称被拒绝，以及构建包包含 Markdown 资源。修改提示词内容时运行相关查询、问答或报告检查，并按需要验证真实模型效果。
