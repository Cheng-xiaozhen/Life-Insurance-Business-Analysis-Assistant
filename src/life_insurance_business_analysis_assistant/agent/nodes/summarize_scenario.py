"""根据全部步骤结论流式生成场景总结，不读取原始数据或重新取数。"""

import json
from typing import TypedDict

from langchain_core.runnables import RunnableConfig

from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.state import AgentState
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt


class SummarizeScenarioUpdate(TypedDict):
    """仅提交完整场景总结。"""

    summary: str


def summarize_scenario(state: AgentState, config: RunnableConfig) -> SummarizeScenarioUpdate:
    """确认步骤完整后，仅抽取编号和结论作为总结依据。"""
    template, index = state["template"], state["step_index"]
    if template is None or state["clarification"] is not None:
        raise ValueError("总结需要已加载模板且没有待解决追问")
    steps = template["steps"]
    results = state["step_results"]
    if not steps or type(index) is not int or index != len(steps):
        raise ValueError("所有分析步骤完成后才能总结")
    if [r["step_id"] for r in results] != [s["step_id"] for s in steps]:
        raise ValueError("步骤结果缺失、重复或顺序不匹配")
    if any(not isinstance(r["conclusion"], str) or not r["conclusion"].strip() for r in results):
        raise ValueError("步骤结论必须是非空文本")
    payload = {
        "scenario": {key: template[key] for key in (
            "name", "analysis_purpose", "channel_type", "time_dimension", "analysis_object"
        )},
        "slots": state["slots"],
        "conclusions": [{"step_id": r["step_id"], "conclusion": r["conclusion"]} for r in results],
    }
    llm = get_llm(thinking=True)
    if llm is None:
        raise RuntimeError("总结模型未配置，请设置 DEEPSEEK_API_KEY")
    stream = llm.stream_events([
        ("system", load_prompt("summarize_scenario")), ("human", json.dumps(payload, ensure_ascii=False)),
    ], config=config, version="v3")
    summary = "".join(stream.text).strip()
    message = stream.output
    if message.tool_calls:
        raise RuntimeError("场景总结不允许调用工具")
    if message.response_metadata.get("finish_reason") in ("length", "content_filter"):
        raise RuntimeError("场景总结未完整生成")
    if not summary:
        raise RuntimeError("总结模型未返回有效文本")
    return SummarizeScenarioUpdate(summary=summary)
