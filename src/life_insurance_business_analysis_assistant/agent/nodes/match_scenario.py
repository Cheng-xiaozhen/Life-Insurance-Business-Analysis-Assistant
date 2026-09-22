"""在小规模场景目录中做语义匹配；所有候选都需要用户确认。"""

import json
from pathlib import Path

from langgraph.constants import TAG_NOSTREAM
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, Field

from life_insurance_business_analysis_assistant.agent.context import AgentContext, load_scenario_catalog
from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.state import AgentState, Clarification, ScenarioCandidate
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt


class ScenarioMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    scenario_id: str
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=1)


class ScenarioMatches(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    candidates: list[ScenarioMatch]


def match_scenario(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    question = state["question"]
    if not isinstance(question, str) or not question.strip():
        raise ValueError("用户问题必须是非空字符串")
    path = runtime.context.template_path
    catalog = load_scenario_catalog(path) if path and Path(path).is_dir() else runtime.context.scenario_catalog
    if not catalog:
        return {"candidates": [], "scenario_id": None, "clarification": None}
    llm = get_llm(thinking=False)
    if llm is None:
        raise RuntimeError("场景匹配模型未配置，请设置 DEEPSEEK_API_KEY")
    raw = llm.with_structured_output(ScenarioMatches, method="function_calling").invoke([
        ("system", load_prompt("match_scenario")),
        ("human", json.dumps({"question": question, "catalog": catalog}, ensure_ascii=False)),
    ], config={"tags": [TAG_NOSTREAM]})
    matches = ScenarioMatches.model_validate(raw)
    entries = {entry["scenario_id"]: entry for entry in catalog}
    ids = [match.scenario_id for match in matches.candidates]
    if len(ids) != len(set(ids)) or set(ids) - entries.keys():
        raise ValueError("模型返回重复或目录中不存在的场景")
    candidates = []
    for match in sorted(matches.candidates, key=lambda item: item.confidence, reverse=True)[:3]:
        entry = entries[match.scenario_id]
        candidates.append(ScenarioCandidate(
            scenario_id=match.scenario_id, name=entry["name"], confidence=match.confidence, reason=match.reason,
            score=float(sum(word in question for word in set(entry["keywords"]))),
        ))
    return {"candidates": candidates, "scenario_id": None, "clarification": Clarification(
        kind="scenario_selection", prompt="请选择并确认本次分析场景。匹配置信度为模型估计，不是正确概率。", slot_issues=[],
    ) if candidates else None}
