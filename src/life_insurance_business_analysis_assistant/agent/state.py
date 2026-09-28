"""单次智能问答的状态契约。

业务字段采用覆盖更新；聊天消息和执行进度使用各自的 reducer。TypedDict 只描述结构，
模板、槽位及外部数据的运行时校验由对应节点负责。
模型、查询客户端、场景目录和 checkpoint 配置不属于业务 State。
"""

from typing import Annotated, Literal, NotRequired, TypeAlias

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict, TypeAliasType


SlotValue: TypeAlias = str | int  # 当前支持的槽位值：文本或整数。
JSONValue = TypeAliasType("JSONValue", (  # 命名递归类型，支持 Studio 生成 JSON Schema。
    str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
))


class ScenarioCandidate(TypedDict):
    """语义匹配得到的候选场景。"""

    scenario_id: str  # 场景唯一编码。
    name: str  # 场景展示名称。
    confidence: float  # 模型评估值，不是经过校准的正确概率。
    reason: str


class SlotDefinition(TypedDict):
    """模板中的槽位声明，不是本次抽取的槽位值。"""

    description: str  # 槽位的业务含义。
    type: Literal["string", "integer"]  # 声明的槽位类型。
    required: bool  # 执行前是否必须有有效值。
    default: NotRequired[SlotValue]  # 仅非必填槽位允许采用默认值。
    minimum: NotRequired[int]  # 整数槽位的最小允许值。
    maximum: NotRequired[int]  # 整数槽位的最大允许值。


class ScenarioStep(TypedDict):
    """一个普通分析步骤的模板配置。"""

    step_id: int  # 模板中的步骤序号，从 1 开始。
    text: str  # 自然语言分析说明，不绑定运行时槽位。
    metrics: list[str]  # 本步骤需要查询的指标。
    analysis_mode: NotRequired[str | None]  # 可选分析模式，如条件筛选。


class ScenarioTemplate(TypedDict):
    """加载器规范化后的模板快照，运行期间不修改。"""

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

    kind: Literal["scenario_selection", "slot_completion"]
    prompt: str  # 展示给用户的追问内容。
    slot_issues: list[SlotIssue]  # 场景选择时为空，候选读取 candidates。


class DatasetRecord(TypedDict):
    """一次成功查询中的一张表；以分析内 dataset_id 为键保存。"""

    step_id: int
    request: dict  # DataQueryRequest 的 JSON 快照。
    payload: dict  # 已经 DatasetPayload 校验的 JSON。


class StepResult(TypedDict):
    step_id: int
    dataset_ids: list[str]
    conclusion_step_ids: list[int]  # 本次提供给分析器的前序结论。
    conclusion: str


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


class AgentState(TypedDict):
    """字段由 create_initial_state 初始化，节点只返回需要覆盖的字段。

    question 保留供场景匹配和展示；slots、user_reply 仅兼容独立槽位组件。
    analyze_step 使用当前步骤数据；无指标步骤读取前序结论。成功后保存结果、
    推进 step_index。原始数据不在各步重复保存。
    失败不推进步骤；总结只读取步骤结论，图表推荐可以读取步骤数据。
    """

    question: str  # 本次分析的原始问题，运行期间保留。
    candidates: list[ScenarioCandidate]  # 本次问题命中的候选场景。
    scenario_id: str | None  # 已选场景编码；None 表示尚未确定。
    template: ScenarioTemplate | None  # 已校验的模板快照；None 表示尚未加载。
    slots: dict[str, SlotValue]  # 兼容字段；不参与当前取数、分析和总结。
    clarification: Clarification | None  # 当前追问；None 表示没有待解决的追问。
    user_reply: str | None  # 用户补充回复
    step_index: int  # 零基列表索引，与模板 step_id 区分。
    datasets: dict[str, DatasetRecord]
    step_results: list[StepResult]  # 按执行顺序保存的已完成步骤结果。
    summary: str | None  # 最后的完整场景总结；None 表示尚未生成。
    chart_recommendations: list[ChartRecommendation] | None  # None 未执行；完成后包含推荐或不推荐决策。


def merge_execution(previous: dict, update: dict) -> dict:
    return {**previous, **update}


class ChatState(AgentState):
    # 在AgentState基础上添加messages字段，用于聊天能力
    messages: Annotated[list[AnyMessage], add_messages]
    analysis_id: str
    last_question: str
    status: str
    execution: Annotated[dict[str, dict], merge_execution]


class StudioInput(TypedDict):
    question: NotRequired[str | None]
    messages: NotRequired[Annotated[list[AnyMessage], add_messages]]


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
        datasets={},
        step_results=[],
        summary=None,
        chart_recommendations=None,
    )



def current_step(state: AgentState) -> ScenarioStep:
    template, index = state["template"], state["step_index"]
    if template is None or type(index) is not int or not 0 <= index < len(template["steps"]):
        raise ValueError("step_index 超出当前模板步骤范围")
    return template["steps"][index]
