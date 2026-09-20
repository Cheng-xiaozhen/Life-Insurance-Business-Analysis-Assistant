"""流式生成当前步骤结论，成功后一次性提交步骤结果。"""

import json
from copy import deepcopy
from typing import TypedDict

from langchain_core.runnables import RunnableConfig

from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.chat import chat_message, stream_text
from life_insurance_business_analysis_assistant.agent.state import AgentState, StepResult
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt


class AnalyzeStepUpdate(TypedDict):
    """完整结论生成后同步保存结果、推进索引并清空当前数据。"""

    step_results: list[StepResult]
    step_index: int
    current_data: None


def analyze_step(state: AgentState, config: RunnableConfig) -> AnalyzeStepUpdate:
    """普通步骤 Prompt 不读取前序结果；片段通过 LangGraph 模型事件输出。"""
    template, index, data = state["template"], state["step_index"], state["current_data"]
    if template is None or data is None or state["clarification"] is not None:
        raise ValueError("分析需要已加载模板、当前数据且没有待解决追问")
    if type(index) is not int or not 0 <= index < len(template["steps"]):
        raise ValueError("step_index 超出当前模板步骤范围")
    step = template["steps"][index]
    llm = get_llm(thinking=True)
    if llm is None:
        raise RuntimeError("分析模型未配置，请设置 DEEPSEEK_API_KEY")
    payload = {
        "scenario": {key: template[key] for key in (
            "name", "analysis_purpose", "channel_type", "time_dimension", "analysis_object"
        )},
        "step": {"step_id": step["step_id"], "text": step["text"],
                 "analysis_mode": step.get("analysis_mode"), "metrics": step["metrics"]},
        "slots": state["slots"], "current_data": data,
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
    result = StepResult(step_id=step["step_id"], data=deepcopy(data), conclusion=conclusion)
    update = AnalyzeStepUpdate(
        step_results=[*state["step_results"], result], step_index=index + 1, current_data=None,
    )
    if state.get("analysis_id"):
        update.update(messages=[chat_message(state, f"step:{step['step_id']}", f"### {heading}\n\n{conclusion}")],
                      status="正在执行下一分析阶段")
    return update
