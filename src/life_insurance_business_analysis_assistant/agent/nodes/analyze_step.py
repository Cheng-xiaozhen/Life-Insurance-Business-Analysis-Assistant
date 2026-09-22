"""流式生成当前步骤结论，成功后一次性提交步骤结果。"""

import json
from copy import deepcopy
from typing import TypedDict

from langchain_core.runnables import RunnableConfig

from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.chat import chat_message, stream_text
from life_insurance_business_analysis_assistant.agent.state import AgentState, StepResult, current_step
from life_insurance_business_analysis_assistant.data_coverage import prepare_step_data
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt


class AnalyzeStepUpdate(TypedDict):
    """完整结论生成后同步保存结果、推进索引并清空当前计划。"""

    step_results: list[StepResult]
    step_index: int
    step_plan: None


def analyze_step(state: AgentState, config: RunnableConfig) -> AnalyzeStepUpdate:
    """只读取计划验证的数据及前序结论；成功后原子提交结果。"""
    step = current_step(state)
    template, index, plan = state["template"], state["step_index"], state["step_plan"]
    if plan is None or plan["step_id"] != step["step_id"] or state["clarification"] is not None:
        raise ValueError("分析需要当前步骤计划且没有待解决追问")
    if [r["step_id"] for r in state["step_results"]] != [s["step_id"] for s in template["steps"][:index]]:
        raise ValueError("前序步骤结果缺失、重复或顺序错误")
    data_uses, datasets = prepare_step_data(plan, state["datasets"])
    results = {r["step_id"]: r for r in state["step_results"]}
    if any(ref not in results for ref in plan["conclusion_step_ids"]):
        raise ValueError("计划引用的前序结论不存在")
    if not datasets and not plan["conclusion_step_ids"]:
        raise ValueError("当前分析没有数据或结论依据")
    llm = get_llm(thinking=True)
    if llm is None:
        raise RuntimeError("分析模型未配置，请设置 DEEPSEEK_API_KEY")
    payload = {
        "question": state["question"],
        "scenario": {key: template[key] for key in (
            "name", "analysis_purpose", "channel_type", "time_dimension", "analysis_object"
        )},
        "step": {"step_id": step["step_id"], "text": step["text"],
                 "analysis_mode": step.get("analysis_mode"), "metrics": step["metrics"]},
        "slots": state["slots"], "datasets": datasets,
        "conclusions": [{"step_id": ref, "conclusion": results[ref]["conclusion"]} for ref in plan["conclusion_step_ids"]],
        "clarification_answers": plan["clarification_answers"],
    }
    heading = f"步骤 {step['step_id']}：{step['text']}"
    conclusion, message = stream_text(llm, [
        ("system", load_prompt("analyze_step")), ("human", json.dumps(payload, ensure_ascii=False)),
    ], config, state, f"step:{step['step_id']}", heading)
    if message.tool_calls:
        raise RuntimeError("分析步骤不允许调用工具")
    if message.response_metadata.get("finish_reason") in ("length", "content_filter"):
        raise RuntimeError("分析结论未完整生成")
    if not conclusion:
        raise RuntimeError("分析模型未返回有效结论")
    result = StepResult(step_id=step["step_id"], data_uses=deepcopy(data_uses),
                        conclusion_step_ids=list(plan["conclusion_step_ids"]), conclusion=conclusion)
    update = AnalyzeStepUpdate(
        step_results=[*state["step_results"], result], step_index=index + 1, step_plan=None,
    )
    if state.get("analysis_id"):
        update.update(messages=[chat_message(state, f"step:{step['step_id']}", f"### {heading}\n\n{conclusion}",
                                            reasoning=message.additional_kwargs.get("analysis_reasoning", ""))],
                      status="正在执行下一分析阶段")
    return update
