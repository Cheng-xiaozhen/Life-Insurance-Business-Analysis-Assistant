"""POC 仅对首步数据作一次图表推荐决策，不取数或绘图。"""

import json
from typing import Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict

from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.state import AgentState, ChartRecommendation
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt


class ChartDecision(BaseModel):
    """模型输出契约；字段存在性和决策一致性由节点校验。"""

    model_config = ConfigDict(extra="forbid", strict=True)
    recommended: bool
    chart_type: Literal["bar", "line", "pie", "scatter"] | None
    step_id: int
    dimensions: list[str]
    metrics: list[str]
    reason: str
    description: str


class RecommendChartsUpdate(TypedDict):
    """只提交一条首步图表决策，包括不推荐的情况。"""

    chart_recommendations: list[ChartRecommendation]


def recommend_charts(state: AgentState, config: RunnableConfig) -> RecommendChartsUpdate:
    """首步数据不足时不转向其他步骤；失败不写入半成品。"""
    template = state["template"]
    if template is None or not template["steps"] or not state["summary"]:
        raise ValueError("图表推荐需要已加载模板及完成的场景总结")
    if state["clarification"] is not None or state["step_index"] != len(template["steps"]):
        raise ValueError("分析尚未完成，不能推荐图表")
    step = template["steps"][0]
    results = [r for r in state["step_results"] if r["step_id"] == step["step_id"]]
    if len(results) != 1:
        raise ValueError("首步分析结果必须唯一存在")
    result = results[0]
    rows = result["data"].get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("POC 图表数据 rows 必须是记录列表")
    columns: list[set[str]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("POC 图表数据 rows 必须是记录列表")
        columns.append(set(row))
    # 只允许每条记录都具备的列，避免推荐缺失列或元数据字段。
    fields = sorted(set.intersection(*columns)) if columns else []
    payload = {
        "analysis_purpose": template["analysis_purpose"],
        "step": {"step_id": step["step_id"], "text": step["text"], "analysis_mode": step.get("analysis_mode")},
        "data": result["data"], "conclusion": result["conclusion"], "available_fields": fields,
    }
    llm = get_llm(thinking=True)
    if llm is None:
        raise RuntimeError("图表推荐模型未配置，请设置 DEEPSEEK_API_KEY")
    raw = llm.with_structured_output(ChartDecision, method="json_mode").invoke([
        ("system", load_prompt("recommend_charts") + json.dumps(ChartDecision.model_json_schema(), ensure_ascii=False)),
        ("human", json.dumps(payload, ensure_ascii=False)),
    ], config=config)
    decision = ChartDecision.model_validate(raw)
    if decision.step_id != step["step_id"]:
        raise ValueError("图表只能引用首步数据")
    if not decision.reason.strip() or not decision.description.strip():
        raise ValueError("推荐原因及解读说明不能为空")
    selected = decision.dimensions + decision.metrics
    if len(set(selected)) != len(selected) or set(selected) - set(fields):
        raise ValueError("图表字段重复或不存在于当前数据")
    if decision.recommended:
        if decision.chart_type is None or not decision.metrics or len(rows) < 2:
            raise ValueError("推荐图表需要有效类型、指标及多个观测点")
        if decision.chart_type == "scatter":
            if len(decision.metrics) != 2:
                raise ValueError("散点图需要两个指标")
        elif not decision.dimensions:
            raise ValueError("该图表需要真实维度")
    elif decision.chart_type is not None or selected:
        raise ValueError("不推荐时图表类型必须为空且不能选择字段")
    recommendation = ChartRecommendation(
        recommended=decision.recommended, chart_type=decision.chart_type,
        step_id=decision.step_id, dimensions=decision.dimensions, metrics=decision.metrics,
        reason=decision.reason, description=decision.description,
    )
    return RecommendChartsUpdate(chart_recommendations=[recommendation])
