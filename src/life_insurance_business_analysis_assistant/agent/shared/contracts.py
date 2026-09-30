"""跨图共享的数据记录和边界字段，不包含业务图的内部执行状态。"""

from typing import Annotated, Literal, NotRequired
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict, TypeAliasType


JSONValue = TypeAliasType("JSONValue", (  # 命名递归类型，支持 Studio 生成 JSON Schema。
    str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
))


class ScenarioStep(TypedDict):
    """一个普通分析步骤的模板配置。"""

    step_id: int  # 模板中的步骤序号，从 1 开始。
    text: str  # 自然语言分析说明。
    metrics: list[str]  # 本步骤需要查询的指标。
    analysis_mode: NotRequired[str | None]  # 可选分析模式，如条件筛选。
    section_id: NotRequired[str]
    section_path: NotRequired[list[str]]
    local_step_id: NotRequired[int]
    guidance: NotRequired[list[str]]
    source_step_ids: NotRequired[list[int]]


class ExecutionTemplate(TypedDict):
    """加载器规范化后的模板快照，运行期间不修改。"""

    scenario_id: NotRequired[str]
    report_id: NotRequired[str]
    name: str  # 场景展示名称。
    channel_type: str  # 场景适用渠道。
    time_dimension: str  # 时间粒度，如月度，不是具体年月。
    analysis_object: str  # 分析对象层级，如机构，不是具体机构范围。
    analysis_purpose: str  # 业务分析目的，如经营检视。
    keywords: NotRequired[list[str]]
    steps: list[ScenarioStep]  # 分析步骤 已按 step_id 排序。
    question: NotRequired[str]
    writing_style: NotRequired[dict[str, JSONValue]]


ScenarioTemplate = ExecutionTemplate


class DatasetRecord(TypedDict):
    """一次成功查询中的一张表；以分析内 dataset_id 为键保存。"""

    step_id: int
    request: dict  # DataQueryRequest 的 JSON 快照。
    payload: dict  # 已经 DatasetPayload 校验的 JSON。


class StepResult(TypedDict):
    """分析步骤的结果"""
    step_id: int # 步骤ID
    dataset_ids: list[str] # 数据集ID列表
    conclusion: str # 结论


class AnalysisExecutionResult(TypedDict):
    """分析子图的唯一输出契约"""
    datasets: dict[str, DatasetRecord] # 已加载的数据集，键为dataset_id
    step_results: list[StepResult] # 已完成的分析步骤结果列表


class ChartRecommendation(TypedDict):
    """基于已有步骤数据的一条图表建议。"""

    recommended: bool  # 是否推荐；不推荐时仍保存原因。
    chart_type: Literal["bar", "line", "pie", "scatter"] | None  # 不推荐时为 None。
    # 每条建议引用一个已使用数据集，不隐式聚合或拼接。
    step_id: int  # 对应模板中的步骤序号。
    dimensions: list[str]  # 图表使用的维度，如机构。
    metrics: list[str]  # 图表使用的指标，如标保达成率。
    description: str  # 说明如何阅读这张图表。
    reason: str  # 推荐或不推荐的原因。
    dataset_id: str | None
    data: list[dict[str, JSONValue]]  # Python 从实际记录组装，LLM 不生成数值。
    units: dict[str, str | None]


def merge_execution(previous: dict, update: dict) -> dict:
    return {**previous, **update}


class BusinessState(TypedDict):
    """业务图边界共用的分析输入与结果。"""
    question: str
    template: ExecutionTemplate | None
    analysis_result: AnalysisExecutionResult | None
    chart_recommendations: list[ChartRecommendation] | None


class MessageState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    analysis_id: str
    last_question: str
    status: str
    execution: Annotated[dict[str, dict], merge_execution]
