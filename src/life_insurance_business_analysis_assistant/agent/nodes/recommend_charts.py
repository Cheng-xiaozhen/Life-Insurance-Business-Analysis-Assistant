"""从各步骤已使用数据推荐图表，并在同一节点验证及组装渲染数据。"""

import json
from datetime import date
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import merge_configs
from langgraph.constants import TAG_NOSTREAM
from pydantic import BaseModel, ConfigDict, Field

from life_insurance_business_analysis_assistant.agent.llm import get_llm
from life_insurance_business_analysis_assistant.agent.chat import AnalysisStream, chat_message
from life_insurance_business_analysis_assistant.agent.state import AgentState
from life_insurance_business_analysis_assistant.data_coverage import canonical, numeric, select_data
from life_insurance_business_analysis_assistant.prompt_loader import load_prompt


class ChartDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    recommended: bool
    chart_type: Literal["bar", "line", "pie", "scatter"] | None
    step_id: int
    candidate_id: str | None = None
    dimensions: list[str]
    metrics: list[str]
    reason: str = Field(min_length=1)
    description: str = Field(min_length=1)


class ChartDecisions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    recommendations: list[ChartDecision] = Field(min_length=1)


def chart_candidates(state: AgentState) -> list[dict]:
    candidates, seen = [], set()
    for result in state["step_results"]:
        for use in result["data_uses"]:
            identity = canonical({key: value for key, value in use.items() if key != "requirement_id"})
            if identity in seen:
                continue
            seen.add(identity)
            dataset = state["datasets"][use["dataset_id"]]
            data = select_data(dataset, use)
            candidates.append({"candidate_id": f"data-{len(candidates) + 1}", "dataset_id": use["dataset_id"],
                               "step_id": result["step_id"], "conclusion": result["conclusion"], "data": data,
                               "dimensions": dataset["coverage"]["dimensions"], "metrics": use["metrics"]})
    return candidates


def assemble_chart(decision: ChartDecision, candidate: dict | None) -> dict:
    result = {key: value for key, value in decision.model_dump().items() if key != "candidate_id"}
    result.update(dataset_id=candidate["dataset_id"] if candidate else None, data=[], units={})
    if not decision.reason.strip() or not decision.description.strip():
        raise ValueError("图表说明不能为空")
    if not decision.recommended:
        if decision.chart_type is not None or decision.dimensions or decision.metrics:
            raise ValueError("不推荐时图表类型和字段必须为空")
        return result
    if candidate is None or decision.step_id != candidate["step_id"]:
        raise ValueError("图表必须引用有效候选及其来源步骤")
    fields = decision.dimensions + decision.metrics
    if len(set(fields)) != len(fields) or set(decision.dimensions) - set(candidate["dimensions"]) or set(decision.metrics) - set(candidate["metrics"]):
        raise ValueError("图表字段重复或不属于实际使用的数据")
    data = candidate["data"]
    try:
        if decision.chart_type is None or not decision.metrics or len(data["rows"]) < 2:
            raise ValueError("缺少图型、指标或多个观测点")
        if not data["complete"]:
            raise ValueError("数据不完整，不能生成可能误导的比较图")
        if decision.chart_type != "scatter" and len(decision.dimensions) != 1:
            raise ValueError("该图型需要一个明确维度")
        if decision.chart_type == "scatter" and len(decision.metrics) != 2:
            raise ValueError("散点图需要两个数值指标")
        if decision.chart_type in ("bar", "line") and len({data["units"][m] for m in decision.metrics}) != 1:
            raise ValueError("同一数值轴不能混用不同单位")
        rows = []
        for row in data["rows"]:
            if any(row.get(d) is None for d in decision.dimensions):
                raise ValueError("图表维度值缺失")
            rows.append({**{d: row[d] for d in decision.dimensions}, **{m: numeric(row.get(m)) for m in decision.metrics}})
        if decision.dimensions:
            keys = [canonical([row[d] for d in decision.dimensions]) for row in rows]
            if len(keys) != len(set(keys)):
                raise ValueError("图表维度重复，不能隐式聚合或覆盖")
        if decision.chart_type == "line":
            dimension = decision.dimensions[0]
            # 时间轴必须由数据源显式声明；不能把机构名称或顺序号当时间。
            if dimension not in data.get("time_dimensions", []):
                raise ValueError("数据未声明真实时间维度")
            for row in rows:
                date.fromisoformat(str(row[dimension]))
            rows.sort(key=lambda row: str(row[dimension]))
        if decision.chart_type == "pie":
            if len(decision.metrics) != 1 or not data.get("partition_of"):
                raise ValueError("数据源未声明互斥且构成整体的份额关系")
            metric = decision.metrics[0]
            if data["units"][metric] == "%" or any(row[metric] < 0 for row in rows) or sum(row[metric] for row in rows) <= 0:
                raise ValueError("比率、负值或零总量不能作为整体份额")
        result["data"] = rows
        result["units"] = {m: data["units"][m] for m in decision.metrics}
    except (ValueError, TypeError) as error:
        result.update(recommended=False, chart_type=None, dimensions=[], metrics=[],
                      reason=f"无法安全组装图表：{error}", description="请阅读步骤结论及数据限制。")
    limitations = []
    if data.get("is_mock"):
        limitations.append("模拟样例，不代表真实经营数据")
    if data.get("notice"):
        limitations.append(str(data["notice"]))
    if any(data["units"][m] is None for m in decision.metrics):
        limitations.append("部分指标单位未知")
    if limitations:
        result["description"] += "（" + "；".join(dict.fromkeys(limitations)) + "）"
    return result


def recommend_charts(state: AgentState, config: RunnableConfig) -> dict:
    template = state["template"]
    if template is None or not state["summary"] or state["clarification"] or state["step_index"] != len(template["steps"]):
        raise ValueError("图表推荐需要完整的步骤结果和场景总结")
    if [r["step_id"] for r in state["step_results"]] != [s["step_id"] for s in template["steps"]]:
        raise ValueError("图表推荐的步骤结果缺失或顺序错误")
    candidates = chart_candidates(state)
    if not candidates:
        return {"chart_recommendations": [assemble_chart(ChartDecision(
            recommended=False, chart_type=None, step_id=template["steps"][-1]["step_id"],
            dimensions=[], metrics=[], reason="没有可用于图表的步骤数据", description="请阅读分析结论。"), None)]}
    llm = get_llm(thinking=True)
    if llm is None:
        raise RuntimeError("图表推荐模型未配置，请设置 DEEPSEEK_API_KEY")
    progress = AnalysisStream(state, "charts", "图表推荐", protocol=False) if state.get("analysis_id") else None
    try:
        raw = llm.with_structured_output(ChartDecisions, method="json_mode").invoke([
            ("system", load_prompt("recommend_charts") + json.dumps(ChartDecisions.model_json_schema(), ensure_ascii=False)),
            ("human", json.dumps({"analysis_purpose": template["analysis_purpose"], "summary": state["summary"],
                                  "candidates": candidates}, ensure_ascii=False)),
        ], config=merge_configs(config, {"tags": [TAG_NOSTREAM], "callbacks": [progress] if progress else []}),
            **({"stream": True} if progress else {}))
    finally:
        if progress:
            progress.flush()
    decisions = ChartDecisions.model_validate(raw)
    by_id = {c["candidate_id"]: c for c in candidates}
    recommendations, seen = [], set()
    valid_steps = {s["step_id"] for s in template["steps"]}
    for decision in decisions.recommendations:
        if decision.step_id not in valid_steps:
            raise ValueError("图表引用未知步骤")
        candidate = by_id.get(decision.candidate_id)
        if decision.candidate_id is not None and candidate is None:
            raise ValueError("图表引用未知候选")
        if candidate and decision.step_id != candidate["step_id"]:
            raise ValueError("图表候选与步骤不匹配")
        identity = (decision.candidate_id, decision.chart_type, tuple(decision.dimensions), tuple(decision.metrics))
        if identity in seen:
            raise ValueError("图表推荐重复")
        seen.add(identity)
        recommendations.append(assemble_chart(decision, candidate))
    update = {"chart_recommendations": recommendations}
    if progress:
        update.update(messages=[chat_message(state, "charts", "### 图表推荐\n\n",
                                            reasoning="".join(progress.reasoning))])
    return update
