from typing import Literal
from typing_extensions import TypedDict
from life_insurance_business_analysis_assistant.agent.shared.contracts import BusinessState, MessageState


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


class AgentState(BusinessState):
    """字段由 create_initial_state 初始化，节点只返回需要覆盖的字段。

    分析循环由独立子图执行，父图只保存完成后的 analysis_result。
    """

    candidates: list[ScenarioCandidate]  # 本次问题命中的候选场景。
    scenario_id: str | None  # 已选场景编码；None 表示尚未确定。
    clarification: Clarification | None  # 当前追问；None 表示没有待解决的追问。
    summary: str | None  # 最后的完整场景总结；None 表示尚未生成。


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


class QuestionAnswerState(AgentState, MessageState):
    """智能问答业务状态及聊天输出。"""
