"""在小规模场景目录中做语义匹配；所有候选都需要用户确认。"""

import json

from langgraph.constants import TAG_NOSTREAM
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, Field

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.state import AgentState, Clarification, ScenarioCandidate
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt


class ScenarioMatch(BaseModel):
    """
    意图识别返回的候选场景
    """
    model_config = ConfigDict(extra="forbid", strict=True) # 严格模式，不允许额外字段，严格类型校验
    scenario_id: str =Field(description="场景编码")
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False,description="匹场景配置信度，取值范围为0-1")
    reason: str = Field(min_length=1,description="模型给出的匹配理由")


class ScenarioMatches(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    candidates: list[ScenarioMatch] = Field(description="匹配到的候选场景列表")


def match_scenario(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    """
    在小规模场景目录中做匹配；所有候选都需要用户确认。
        Args:
            state: 当前Agent的State
            runtime: Agent运行时环境
        Returns:
            匹配结果
    """
    question = state["question"] # 用户输入的问题
    if not isinstance(question, str) or not question.strip():
        raise ValueError("用户问题必须是非空字符串")
    
    catalog = runtime.context.scenario_catalog
    if not catalog:
        return {"candidates": [], "scenario_id": None, "clarification": None}
    
    llm = get_llm(thinking=False)
    if llm is None:
        raise RuntimeError("场景匹配模型未配置，请设置 DEEPSEEK_API_KEY")
    
    raw = llm.with_structured_output(ScenarioMatches, method="function_calling").invoke([
        ("system", load_prompt("match_scenario")),
        ("human", json.dumps({"question": question, "catalog": catalog}, ensure_ascii=False)),
    ], config={"tags": [TAG_NOSTREAM]}) # 调用LLM进行场景匹配，使用模型的函数调用能力生成结构化结果；config中设置TAG_NOSTREAM，表示不使用流式输出，避免匹配过程的模型输出被前端当做分析过程展示

    matches = ScenarioMatches.model_validate(raw) # 验证模型输出，确保符合预期的结构

    entries = {entry["scenario_id"]: entry for entry in catalog} # 场景列表
    ids = [match.scenario_id for match in matches.candidates] # 模型返回的候选场景ID列表

    if len(ids) != len(set(ids)) or set(ids) - entries.keys():
        # 避免重复候选 和 模型幻觉场景
        raise ValueError("模型返回重复或目录中不存在的场景")
    
    candidates = []
    for match in sorted(matches.candidates, key=lambda item: item.confidence, reverse=True)[:3]:
        entry = entries[match.scenario_id]
        candidates.append(ScenarioCandidate(
            scenario_id=match.scenario_id, name=entry["name"], confidence=match.confidence, reason=match.reason,
        ))
    return {"candidates": candidates, "scenario_id": None, "clarification": Clarification(
        kind="scenario_selection", prompt="请选择并确认本次分析场景。", slot_issues=[],
    ) if candidates else None}
