"""单次智能问答及其补参过程的状态契约。

所有字段采用覆盖更新，不配置追加 reducer。TypedDict 只描述结构，
模板、槽位及外部数据的运行时校验由对应节点负责。
模型、查询客户端、场景目录和 checkpoint 配置不属于业务 State。
"""

from typing import Literal, NotRequired, TypeAlias
from typing_extensions import TypedDict, TypeAliasType


SlotValue: TypeAlias = str | int  # 当前支持的槽位值：文本或整数。
JSONValue = TypeAliasType("JSONValue", (  # 命名递归类型，支持 Studio 生成 JSON Schema。
    str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
))
# 问数 API 契约确认后细化字段；此处不预设数据粒度或单位。
StepData: TypeAlias = dict[str, JSONValue]


class ScenarioCandidate(TypedDict):
    """关键词匹配得到的一个候选场景。"""

    scenario_id: str  # 场景唯一编码。
    name: str  # 场景展示名称。
    score: float  # 规则匹配分数。


class SlotDefinition(TypedDict):
    """模板中的槽位声明，不是本次抽取的槽位值。"""

    description: str  # 槽位的业务含义。
    type: Literal["string", "integer"]  # 声明的槽位类型。
    required: bool  # 执行前是否必须有有效值。
    default: NotRequired[SlotValue]  # 用户未提供时可采用的默认值。
    minimum: NotRequired[int]  # 整数槽位的最小允许值。
    maximum: NotRequired[int]  # 整数槽位的最大允许值。


class ScenarioStep(TypedDict):
    """一个普通分析步骤的模板配置。"""

    step_id: int  # 模板中的步骤序号，从 1 开始。
    text: str  # 自然语言分析说明，可含槽位占位符。
    metrics: list[str]  # 本步骤需要查询的指标。
    analysis_mode: NotRequired[str | None]  # 可选分析模式，如条件筛选。
    query_params: dict[str, SlotValue]  # 取数参数及其槽位绑定，如年份对应 {{年份}}。


class ScenarioTemplate(TypedDict):
    """加载器规范化后的模板快照，保留占位符，运行期间不修改。"""

    scenario_id: str  # 场景唯一编码。
    name: str  # 场景展示名称。
    channel_type: str  # 场景适用渠道，不自动充当槽位默认值。
    time_dimension: str  # 时间粒度，如月度，不是具体年月。
    analysis_object: str  # 分析对象层级，如机构，不是具体机构范围。
    analysis_purpose: str  # 业务分析目的，如经营检视。
    keywords: list[str]  # 用于匹配场景的触发关键词。
    slot_definitions: dict[str, SlotDefinition]  # 以参数名为键的槽位声明。
    steps: list[ScenarioStep]  # 分析步骤 已按 step_id 排序。


class SlotIssue(TypedDict):
    """一个尚未解决的槽位问题。"""

    slot_name: str  # 需要补充或修正的槽位名。
    reason: Literal["missing", "ambiguous", "invalid"]  # 分别表示缺失、有歧义或值无效。
    message: str  # 该槽位需要追问的具体原因。


class Clarification(TypedDict):
    """中断时需要用户回答的问题。"""

    kind: Literal["scenario_selection", "slot_completion"]  # 选择场景或补齐槽位。
    prompt: str  # 展示给用户的追问内容。
    slot_issues: list[SlotIssue]  # 场景选择时为空，候选读取 candidates。


class StepResult(TypedDict):
    """一个已成功完成的步骤及其分析结论。"""

    step_id: int  # 对应模板中的步骤序号。
    data: StepData  # 该步骤实际用于分析的数据。
    conclusion: str  # 完整步骤结论，不保存流式片段。


class ChartRecommendation(TypedDict):
    """基于已有步骤数据的一条图表建议。"""

    recommended: bool  # 是否推荐；不推荐时仍保存原因。
    chart_type: Literal["bar", "line", "pie", "scatter"] | None  # 不推荐时为 None。
    # ponytail: POC 每条建议引用一个步骤，跨步骤合并规则确认后再扩展。
    step_id: int  # 对应模板中的步骤序号。
    dimensions: list[str]  # 图表使用的维度，如机构。
    metrics: list[str]  # 图表使用的指标，如标保达成率。
    description: str  # 说明如何阅读这张图表。
    reason: str  # 推荐或不推荐的原因。


class AgentState(TypedDict):
    """字段由 create_initial_state 初始化，节点只返回需要覆盖的字段。

    question 始终保留；补参使用已有槽位、当前追问和最新回复，不存完整历史。
    无效或有歧义的明确修正应移除对应旧槽位并追问，不回退到默认值。
    analyze_step 的 prompt 不读取前序结果；成功后同时保存完整结果、
    推进 step_index 并清空 current_data。流式片段不写入 State。
    失败不推进步骤；总结只读取步骤结论，图表推荐可以读取步骤数据。
    """

    question: str  # 本次分析的原始问题，运行期间保留。
    candidates: list[ScenarioCandidate]  # 本次问题命中的候选场景。
    scenario_id: str | None  # 已选场景编码；None 表示尚未确定。
    template: ScenarioTemplate | None  # 已校验的模板快照；None 表示尚未加载。
    slots: dict[str, SlotValue]  # 已通过校验的槽位值，包含有效默认值。
    clarification: Clarification | None  # 当前追问；None 表示没有待解决的追问。
    user_reply: str | None  # 最新槽位回复，resolve_slots 处理后清空。
    step_index: int  # 零基列表索引，与模板 step_id 区分。
    current_data: StepData | None  # 当前步骤取数结果，None 表示尚未取数，不能用空数据代表失败。
    step_results: list[StepResult]  # 按执行顺序保存的已完成步骤结果。
    summary: str | None  # 最后的完整场景总结；None 表示尚未生成。
    chart_recommendations: list[ChartRecommendation] | None  # None 未执行；POC 保存一条推荐决策。


def create_initial_state(question: str) -> AgentState:
    """为一次新分析创建独立状态；问题有效性由调用入口校验。"""
    return AgentState(
        question=question,
        candidates=[],
        scenario_id=None,
        template=None,
        slots={},
        clarification=None,
        user_reply=None,
        step_index=0,
        current_data=None,
        step_results=[],
        summary=None,
        chart_recommendations=None,
    )
