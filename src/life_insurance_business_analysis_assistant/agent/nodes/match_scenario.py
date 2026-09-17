"""按触发关键词匹配场景，不调用 LLM 或执行后续节点。"""

from typing import TypedDict

from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.state import (
    AgentState,
    Clarification,
    ScenarioCandidate,
)


class MatchScenarioUpdate(TypedDict):
    """匹配节点只覆盖这三个 State 字段。"""

    candidates: list[ScenarioCandidate]
    scenario_id: str | None
    clarification: Clarification | None


def match_scenario(
    state: AgentState, runtime: Runtime[AgentContext]
) -> MatchScenarioUpdate:
    """分数为不同关键词命中数；多命中始终交给用户选择。"""
    question = state["question"]
    if not isinstance(question, str) or not question.strip():
        raise ValueError("用户问题必须是非空字符串")

    candidates: list[ScenarioCandidate] = []
    for entry in runtime.context.scenario_catalog:
        # ponytail: POC 使用字面子串匹配，需理解否定或同义表达时再调整规则。
        score = sum(word in question for word in set(entry["keywords"]))
        if score:
            candidates.append(ScenarioCandidate(
                scenario_id=entry["scenario_id"], name=entry["name"], score=float(score)
            ))
    candidates.sort(key=lambda candidate: candidate["score"], reverse=True)

    clarification: Clarification | None = None
    if len(candidates) > 1:
        clarification = Clarification(
            kind="scenario_selection",
            prompt="匹配到多个场景，请选择一个场景继续分析。分数为规则匹配分数，不是正确概率。",
            slot_issues=[],
        )
    # 零命中的换问法提示与结束路由留给编排/输出层，不冒用 summary。
    return MatchScenarioUpdate(
        candidates=candidates,
        scenario_id=candidates[0]["scenario_id"] if len(candidates) == 1 else None,
        clarification=clarification,
    )
