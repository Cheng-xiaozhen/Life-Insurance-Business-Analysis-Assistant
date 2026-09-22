"""LLM 抽取用户表达，代码合并和校验模板槽位。"""

import json
import logging
from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field
from langgraph.constants import TAG_NOSTREAM

from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.state import (
    AgentState, Clarification, SlotIssue, SlotValue,
)
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


class SlotExtraction(BaseModel):
    """只记录本轮明确提供的值和歧义，不生成默认值或必填判断。"""

    model_config = ConfigDict(extra="forbid", strict=True) # 禁止额外字段和严格模式
    values: dict[str, Any] = Field(description="本轮明确提供的槽位值；保留原类型，无效值也交给代码检查")
    ambiguous: dict[str, str] = Field(description="本轮有歧义的槽位名及原因；不确定时不能猜值")


class ResolveSlotsUpdate(TypedDict):
    """只更新槽位和补参状态。"""

    slots: dict[str, SlotValue]
    clarification: Clarification | None
    user_reply: None


def resolve_slots(state: AgentState) -> ResolveSlotsUpdate:
    """保留未解决问题；有效补充才能解除歧义或无效修正。"""
    template = state["template"]
    if template is None:
        raise ValueError("resolve_slots 需要已加载的模板")
    definitions = template["slot_definitions"]
    llm = get_llm(thinking=False)
    if llm is None:
        raise RuntimeError("槽位抽取模型未配置，请设置 DEEPSEEK_API_KEY")
    payload = {
        "question": state["question"], "user_reply": state["user_reply"],
        "existing_slots": state["slots"], "clarification": state["clarification"],
        "slot_definitions": {name: {"description": d["description"], "type": d["type"]}
                             for name, d in definitions.items()},
    } # 传给 LLM 的 JSON 结构，包含原始问题、用户最新补充、已保存的槽位、当前追问、模板声明的槽位及其类型
    try:
        raw = llm.with_structured_output(SlotExtraction, method="function_calling").invoke([
            ("system", load_prompt("resolve_slots")), ("human", json.dumps(payload, ensure_ascii=False)),
        ], config={"tags": [TAG_NOSTREAM]}) # 内部结构化结果不作为聊天文本输出。
    except Exception:
        logger.exception("resolve_slots 模型调用失败（包含底层异常链）")
        raise
    extraction = SlotExtraction.model_validate(raw) # 再次验证模型输出是否符合结构
    names = set(extraction.values) | set(extraction.ambiguous)
    if names - definitions.keys() or extraction.values.keys() & extraction.ambiguous.keys():
        # 模型返回了模板为生命的槽位 | 同一个槽位同时出现在values和ambiguous中，互相冲突
        raise ValueError("模型返回未声明槽位或相互冲突的抽取结果")

    slots = dict(state["slots"]) # 复制已有槽位，后续修改的是局部变量slots，而不是直接修改state["slots"]，最终通过返回值让LangGraph合并更新
    if slots.keys() - definitions.keys():
        raise ValueError("运行状态包含未声明槽位")
    previous = state["clarification"] # 复制上一轮的补参状态，后续修改的是局部变量previous，而不是直接修改state["clarification"]，最终通过返回值让LangGraph合并更新
    issues = {issue["slot_name"]: issue for issue in previous["slot_issues"]} if (
        previous and previous["kind"] == "slot_completion"
    ) else {} # 如果上一次是槽位补充追问，就把之前的问题转换为字典，方便按槽位名更新
    for name, value in extraction.values.items(): # 处理本轮明确提供的槽位值
        slots[name] = value # 更新槽位值
        issues.pop(name, None) # 移除该槽位原来的问题
    for name, reason in extraction.ambiguous.items(): # 处理本轮有歧义的槽位
        slots.pop(name, None) # 移除该槽位的值，因为它有歧义
        issues[name] = SlotIssue(slot_name=name, reason="ambiguous", message=reason or "请明确该参数")

    for name, definition in definitions.items():
        # 无效或歧义修正不能被默认值掩盖；未提及的问题继续保留。
        if name in issues and issues[name]["reason"] != "missing":
            slots.pop(name, None)
            continue
        if name not in slots and "default" in definition and not definition["required"]:
            slots[name] = definition["default"]
        if name not in slots:
            if definition["required"]:
                issues[name] = SlotIssue(slot_name=name, reason="missing", message=definition["description"])
            else:
                issues.pop(name, None)
            continue
        value = slots[name]
        error = None
        if definition["type"] == "integer":
            if type(value) is not int:
                error = "必须是整数"
            elif "minimum" in definition and value < definition["minimum"]:
                error = f"不能小于 {definition['minimum']}"
            elif "maximum" in definition and value > definition["maximum"]:
                error = f"不能大于 {definition['maximum']}"
        elif not isinstance(value, str) or not value.strip():
            error = "必须是非空字符串"
        if error:
            slots.pop(name)
            issues[name] = SlotIssue(slot_name=name, reason="invalid", message=error)
        else:
            issues.pop(name, None)
    clarification: Clarification | None = None
    if issues:
        ordered = [issues[name] for name in definitions if name in issues]
        clarification = Clarification(
            kind="slot_completion",
            prompt="请补充或修正以下参数：" + "；".join(
                f"{item['slot_name']}（{item['message']}）" for item in ordered
            ), slot_issues=ordered,
        )
    return ResolveSlotsUpdate(slots=slots, clarification=clarification, user_reply=None)
