"""LLM 提取业务需求；Python 校验口径、选择已有数据并生成缺口查询。"""

import json
import logging
import re
from copy import deepcopy

from langgraph.constants import TAG_NOSTREAM
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, Field

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.state import (
    AgentState, Clarification, DataFilter, DataRequirement, StepPlan, current_step,
)
from life_insurance_business_analysis_assistant.data_coverage import choose_data, metric_ranges, validate_requirement
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


class RequirementIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    metrics: list[str] = Field(min_length=1)
    grain: str
    month_offset: int = Field(ge=-1200, le=1200, description="相对于已确认年月的月份偏移；本期0，上月-1，上年同期-12")
    filters: list[DataFilter] = Field(description="额外范围约束；分析阈值留在步骤文本中，不提前过滤完整明细")


class StepIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requirements: list[RequirementIntent]
    conclusion_step_ids: list[int]
    clarification: str | None
    reason: str = Field(min_length=1)


def bind_step_params(state: AgentState) -> dict:
    """兼容旧模板参数，不允许固定值悄悄覆盖已确认槽位。"""
    step, slots = current_step(state), state["slots"]
    params = dict(slots)
    template = state["template"]
    for key, value in (("渠道", template["channel_type"]), ("机构范围", template["analysis_object"])):
        if key in params and params[key] != value:
            raise ValueError(f"查询范围与场景模板冲突: {key}")
        params[key] = value
    pattern = r"\{\{([^{}]+)\}\}"
    for key, value in step["query_params"].items():
        if isinstance(value, str):
            def read(match):
                if match[1] not in slots:
                    raise ValueError(f"查询参数缺少槽位: {match[1]}")
                return slots[match[1]]
            match = re.fullmatch(pattern, value)
            value = read(match) if match else re.sub(pattern, lambda match: str(read(match)), value)
        if key in params and (type(params[key]) is not type(value) or params[key] != value):
            raise ValueError(f"模板取数参数与已确认槽位冲突: {key}")
        params[key] = value
    return params


def plan_step(state: AgentState, runtime: Runtime[AgentContext]) -> dict:
    step = current_step(state)
    if state["clarification"] and state["clarification"]["kind"] != "step_clarification":
        raise ValueError("步骤规划前必须完成场景确认")
    previous = state["step_plan"]
    if previous and previous["step_id"] != step["step_id"]:
        raise ValueError("执行计划与当前步骤不匹配")
    answers = deepcopy(previous["clarification_answers"]) if previous else []
    if state["clarification"]:
        if not state["user_reply"]:
            raise ValueError("步骤追问尚未收到回复")
        answers.append({"question": state["clarification"]["prompt"], "answer": state["user_reply"]})
    capabilities = runtime.context.query_capabilities
    params = bind_step_params(state)
    payload = {
        "question": state["question"], "step": step, "slots": state["slots"], "query_params": params,
        "conclusions": [{"step_id": r["step_id"], "conclusion": r["conclusion"]} for r in state["step_results"]],
        "datasets": [{"dataset_id": key, **{field: value for field, value in record.items() if field != "data"}}
                     for key, record in state["datasets"].items()],
        "query_capabilities": capabilities, "clarification_answers": answers,
    }
    llm = get_llm(thinking=False)
    if llm is None:
        raise RuntimeError("步骤规划模型未配置，请设置 DEEPSEEK_API_KEY")
    raw = llm.with_structured_output(StepIntent, method="function_calling").invoke([
        ("system", load_prompt("plan_step")), ("human", json.dumps(payload, ensure_ascii=False)),
    ], config={"tags": [TAG_NOSTREAM]})
    intent = StepIntent.model_validate(raw)
    completed = {r["step_id"] for r in state["step_results"]}
    if len(set(intent.conclusion_step_ids)) != len(intent.conclusion_step_ids) or any(
        ref not in completed or ref >= step["step_id"] for ref in intent.conclusion_step_ids
    ):
        raise ValueError("Planner 引用了未完成或重复的步骤结论")
    plan = StepPlan(step_id=step["step_id"], requirements=[], data_uses=[], queries=[],
                    conclusion_step_ids=intent.conclusion_step_ids, clarification_answers=answers, reason=intent.reason)
    if intent.clarification is not None:
        if not intent.clarification.strip() or intent.requirements:
            raise ValueError("澄清问题不能为空，且澄清前不能同时执行查询")
        return {"step_plan": plan, "user_reply": None, "clarification": Clarification(
            kind="step_clarification", prompt=intent.clarification.strip(), slot_issues=[])}
    if not intent.requirements and not intent.conclusion_step_ids:
        raise ValueError("直接分析必须有数据需求或已完成结论依据")
    if intent.requirements:
        if capabilities is None:
            raise ValueError("尚未配置问数能力与指标目录，不能推断数据覆盖")
        requested = {m for item in intent.requirements for m in item.metrics}
        if requested != set(step["metrics"]):
            raise ValueError("步骤需求与模板声明指标不一致，不能静默增加或遗漏指标")
        for index, item in enumerate(intent.requirements, 1):
            if item.grain not in capabilities["grains"] or any(
                m not in capabilities["metrics"] or item.grain not in capabilities["metrics"][m]["grains"] for m in item.metrics
            ):
                raise ValueError("问数服务不支持步骤所需指标或粒度")
            year, month = params.get("年份"), params.get("月份")
            if type(year) is not int or type(month) is not int or not 1 <= month <= 12:
                raise ValueError("当前问数能力需要明确的年份和月份")
            shifted_year, shifted_month = divmod(year * 12 + month - 1 + item.month_offset, 12)
            requirement = DataRequirement(
                requirement_id=f"{step['step_id']}:{index}", metrics=item.metrics,
                time_ranges=metric_ranges(item.metrics, shifted_year, shifted_month + 1, capabilities),
                grain=item.grain, dimensions=capabilities["grains"][item.grain],
                scope={key: value for key, value in params.items() if key not in ("年份", "月份")},
                filters=item.filters, completeness="full",
            )
            validate_requirement(requirement)
            uses, queries = choose_data(requirement, state["datasets"], capabilities)
            plan["requirements"].append(requirement)
            plan["data_uses"].extend(uses)
            plan["queries"].extend(queries)
    logger.info("step_id=%s planned requirements=%s reused=%s queries=%s conclusions=%s",
                step["step_id"], len(plan["requirements"]), len(plan["data_uses"]), len(plan["queries"]), intent.conclusion_step_ids)
    return {"step_plan": plan, "clarification": None, "user_reply": None}
