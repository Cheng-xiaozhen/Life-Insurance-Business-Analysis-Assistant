"""单次智能问答的状态契约。

业务字段采用覆盖更新；聊天消息和执行进度使用各自的 reducer。TypedDict 只描述结构，
模板及外部数据的运行时校验由对应节点负责。
模型、查询客户端、场景目录和 checkpoint 配置不属于业务 State。
"""

from typing import Annotated, Literal, NotRequired

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict, TypeAliasType

from .contracts import ScenarioTemplate
from .subgraphs.analysis_execution.state import AnalysisExecutionResult


JSONValue = TypeAliasType("JSONValue", (  # 命名递归类型，支持 Studio 生成 JSON Schema。
    str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
))


class ScenarioCandidate(TypedDict):
    """语义匹配得到的候选场景。"""

    scenario_id: str  # 场景唯一编码。
    name: str  # 场景展示名称。
    confidence: float  # 模型评估值，不是经过校准的正确概率。
    reason: str


class Clarification(TypedDict):
    """中断时需要用户回答的问题。"""

    kind: Literal["scenario_selection"]
    prompt: str  # 展示给用户的追问内容。


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

    分析循环由独立子图执行，父图只保存完成后的 analysis_result。
    """

    question: str  # 本次分析的原始问题，运行期间保留。
    candidates: list[ScenarioCandidate]  # 本次问题命中的候选场景。
    scenario_id: str | None  # 已选场景编码；None 表示尚未确定。
    template: ScenarioTemplate | None  # 已校验的模板快照；None 表示尚未加载。
    clarification: Clarification | None  # 当前追问；None 表示没有待解决的追问。
    analysis_result: AnalysisExecutionResult | None
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
        clarification=None,
        analysis_result=None,
        summary=None,
        chart_recommendations=None,
    )
