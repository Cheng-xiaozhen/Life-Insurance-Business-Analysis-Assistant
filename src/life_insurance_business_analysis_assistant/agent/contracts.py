"""父子工作流共用的模板和数据契约。"""
from typing import NotRequired
from typing_extensions import TypedDict


class ScenarioStep(TypedDict):
    """一个普通分析步骤的模板配置。"""

    step_id: int  # 模板中的步骤序号，从 1 开始。
    text: str  # 自然语言分析说明。
    metrics: list[str]  # 本步骤需要查询的指标。
    analysis_mode: NotRequired[str | None]  # 可选分析模式，如条件筛选。


class ScenarioTemplate(TypedDict):
    """加载器规范化后的模板快照，运行期间不修改。"""

    scenario_id: str  # 场景唯一编码。
    name: str  # 场景展示名称。
    channel_type: str  # 场景适用渠道。
    time_dimension: str  # 时间粒度，如月度，不是具体年月。
    analysis_object: str  # 分析对象层级，如机构，不是具体机构范围。
    analysis_purpose: str  # 业务分析目的，如经营检视。
    keywords: list[str]  # 用于匹配场景的触发关键词。
    steps: list[ScenarioStep]  # 分析步骤 已按 step_id 排序。


class DatasetRecord(TypedDict):
    """一次成功查询中的一张表；以分析内 dataset_id 为键保存。"""

    step_id: int
    request: dict  # DataQueryRequest 的 JSON 快照。
    payload: dict  # 已经 DatasetPayload 校验的 JSON。


