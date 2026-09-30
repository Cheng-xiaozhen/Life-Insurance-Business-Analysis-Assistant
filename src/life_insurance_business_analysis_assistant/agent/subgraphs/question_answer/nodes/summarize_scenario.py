"""根据全部步骤结论及其引用数据流式生成场景总结。"""

import json
from typing import TypedDict
from langchain_core.runnables import RunnableConfig
from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.shared.messages import chat_message, stream_text
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.state import AgentState
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt


class SummarizeScenarioUpdate(TypedDict):
    """仅提交完整场景总结。"""

    summary: str


def summarize_scenario(state: AgentState, config: RunnableConfig) -> SummarizeScenarioUpdate:
    """
    汇总所有的原子结论和它们引用的数据，形成一个场景级最终结论
    """
    template, analysis = state["template"], state["analysis_result"]
    if template is None or state["clarification"] is not None:
        raise ValueError("总结需要已加载模板且没有待解决追问")
    
    steps = template["steps"]
    if not steps or analysis is None:
        raise ValueError("所有分析步骤完成后才能总结")
    
    results = analysis["step_results"]
    if [r["step_id"] for r in results] != [s["step_id"] for s in steps]:
        raise ValueError("步骤结果缺失、重复或顺序不匹配")
    if any(not isinstance(r["conclusion"], str) or not r["conclusion"].strip() for r in results):
        raise ValueError("步骤结论必须是非空文本")
    
    datasets = {}
    for result in results:
        for dataset_id in result["dataset_ids"]:
            record = analysis["datasets"].get(dataset_id)
            if record is None or record["step_id"] != result["step_id"]:
                raise ValueError("总结引用的数据集不存在或来源步骤不匹配")
            datasets[dataset_id] = record["payload"]
    
    payload = {
        "scenario": {key: template[key] for key in (
            "name", "analysis_purpose", "channel_type", "time_dimension", "analysis_object"
        )},
        "step_results": results,
        "datasets": datasets,
    }
    llm = get_llm(thinking=True)
    if llm is None:
        raise RuntimeError("总结模型未配置，请设置 DEEPSEEK_API_KEY")
    
    summary, message = stream_text(
        llm, [
        ("system", load_prompt("summarize_scenario")),
        ("human", json.dumps(payload, ensure_ascii=False)),
    ], config, state, "summary", "场景总结")
    
    if message.tool_calls:
        raise RuntimeError("场景总结不允许调用工具")
    if message.response_metadata.get("finish_reason") in ("length", "content_filter"):
        raise RuntimeError("场景总结未完整生成")
    if not summary:
        raise RuntimeError("总结模型未返回有效文本")
    
    update = SummarizeScenarioUpdate(summary=summary)
    if state.get("analysis_id"): # 是不是Chat模式
        update.update(
            messages=[
                chat_message(
                    state,
                    "summary",
                    f"### 场景总结\n\n{summary}",
                    reasoning=message.additional_kwargs.get("analysis_reasoning", "")
                        )
                    ],
            status="正在生成图表推荐")
    return update
