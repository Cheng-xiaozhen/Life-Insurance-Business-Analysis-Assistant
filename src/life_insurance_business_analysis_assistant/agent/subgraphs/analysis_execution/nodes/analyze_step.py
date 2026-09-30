"""流式生成当前步骤结论，成功后一次性提交步骤结果。"""

import json
from typing import TypedDict

from langchain_core.runnables import RunnableConfig

from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.chat import stream_text
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.state import AnalysisExecutionState, StepResult, get_current_step
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.nodes.fetch_step_data import build_request, saved_step_data
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt


class AnalyzeStepUpdate(TypedDict):
    """完整结论生成后同步保存结果、推进索引。"""

    step_results: list[StepResult]
    step_index: int


def analyze_step(state: AnalysisExecutionState, config: RunnableConfig) -> AnalyzeStepUpdate:
    """
    根据当前分析步骤，读取该步骤允许使用的证据，调用分析 LLM 生成结论；
    只有结论完整生成并校验通过后，才保存当前步骤结果并把 step_index 推进到下一步。
    """
    step = get_current_step(state) # 获取当前步骤信息
    template, index = state["template"], state["step_index"] # 获取模板和步骤索引

    if [r["step_id"] for r in state["step_results"]] != [s["step_id"] for s in template["steps"][:index]]:
        # 检查前序步骤结果是否完整、顺序正确
        raise ValueError("前序步骤结果缺失、重复或顺序错误") 
    
    dataset_ids, datasets, conclusions = [], [], []
    if step["metrics"]: # 有指标步骤
        dataset_ids, datasets = saved_step_data(state, build_request(state))
        if not datasets:
            raise ValueError("当前步骤尚未成功取数")
    else: # 当前步骤无关联指标
        if any(record["step_id"] == step["step_id"] for record in state["datasets"].values()):
            raise ValueError("无指标步骤不能关联旧查询数据") # 如果这个步骤声明没有指标，但却有旧数据集关联，说明数据不一致
        conclusions = [{"step_id": r["step_id"], "conclusion": r["conclusion"]} for r in state["step_results"]] # 把之前完成步骤的结论拿出来，基于已有原子结论进行二次综合
        if "source_step_ids" in step:
            allowed = step["source_step_ids"]
            if not set(allowed) <= {r["step_id"] for r in conclusions}:
                raise ValueError("总结引用了尚未完成的步骤")
            conclusions = [r for r in conclusions if r["step_id"] in allowed]
    
    llm = get_llm(thinking=True)

    if llm is None:
        raise RuntimeError("分析模型未配置，请设置 DEEPSEEK_API_KEY")
    
    payload = {
        "scenario": {
            key: template[key]
              for key in (
                "name",
                "analysis_purpose",
                "channel_type",
                "time_dimension",
                "analysis_object"
        )},
        "step": {
            "step_id": step["step_id"],
            "text": step["text"],
            "analysis_mode": step.get("analysis_mode"),
            "metrics": step["metrics"]
            },
        "datasets": [
            {"dataset_id": key, **data}
            for key, data in zip(dataset_ids, datasets)
            ],
        "conclusions": conclusions,
    }
    if "report_id" in template:
        payload["report"] = payload.pop("scenario")
        payload.update(question=template["question"], writing_style=template["writing_style"],
                       section_path=step["section_path"], guidance=step["guidance"])
    heading = f"步骤 {step['step_id']}：{step['text']}"
    conclusion, message = stream_text(
        llm, 
        [
            ("system", load_prompt("analyze_step")),
            ("human", json.dumps(payload, ensure_ascii=False)),
    ],
    config,
    state,
    f"step:{step['step_id']}",
    heading
    )
    
    if message.tool_calls:
        raise RuntimeError("分析步骤不允许调用工具")
    if message.response_metadata.get("finish_reason") in ("length", "content_filter"):
        raise RuntimeError("分析结论未完整生成")
    if not conclusion:
        raise RuntimeError("分析模型未返回有效结论")
    
    result = StepResult(
        step_id=step["step_id"],
        dataset_ids=dataset_ids,
        conclusion=conclusion
        )
    update = AnalyzeStepUpdate(step_results=[*state["step_results"], result], step_index=index + 1)
    return update
