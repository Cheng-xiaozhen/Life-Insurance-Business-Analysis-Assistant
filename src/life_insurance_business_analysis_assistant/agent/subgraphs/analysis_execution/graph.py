"""单入口、单出口的分析循环；继承父图 checkpointer。"""
from typing import Literal

from langgraph.graph import END, START, StateGraph

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from .analyze_step import analyze_step
from .fetch_step_data import fetch_step_data
from .state import AnalysisExecutionInput, AnalysisExecutionOutput, AnalysisExecutionState


def initialize_subgraph(state: AnalysisExecutionInput) -> dict:
    if not state["template"]["steps"]:
        raise ValueError("分析模板必须包含步骤")
    return {"step_index": 0, "current_step": None, "datasets": {}, "step_results": []}


def load_step(state: AnalysisExecutionState) -> dict:
    steps, index = state["template"]["steps"], state["step_index"]
    if type(index) is not int or not 0 <= index < len(steps):
        raise ValueError("step_index 超出当前模板步骤范围")
    step = steps[index]
    if (not isinstance(step, dict) or type(step.get("step_id")) is not int
            or step["step_id"] != index + 1
            or not isinstance(step.get("text"), str) or not step["text"].strip()
            or not isinstance(step.get("metrics"), list)
            or any(not isinstance(m, str) or not m.strip() for m in step["metrics"])
            or len(set(step["metrics"])) != len(step["metrics"])):
        raise ValueError("当前分析步骤不合法")
    return {"current_step": step}


def route_current_step(state: AnalysisExecutionState) -> Literal["fetch_step_data", "analyze_step"]:
    return "fetch_step_data" if state["current_step"]["metrics"] else "analyze_step"


def route_analysis(state: AnalysisExecutionState) -> Literal["load_step", "finalize_subgraph"]:
    index, count = state["step_index"], len(state["template"]["steps"])
    if type(index) is not int or not 0 <= index <= count:
        raise ValueError("分析后的 step_index 超出模板范围")
    return "load_step" if index < count else "finalize_subgraph"


def finalize_subgraph(state: AnalysisExecutionState) -> AnalysisExecutionOutput:
    steps, results = state["template"]["steps"], state["step_results"]
    if not steps or type(state["step_index"]) is not int or state["step_index"] != len(steps):
        raise ValueError("所有分析步骤完成后才能组装结果")
    if [r["step_id"] for r in results] != [s["step_id"] for s in steps]:
        raise ValueError("步骤结果缺失、重复或顺序不匹配")
    for result in results:
        if not isinstance(result["conclusion"], str) or not result["conclusion"].strip():
            raise ValueError("步骤结论必须是非空文本")
        for dataset_id in result["dataset_ids"]:
            record = state["datasets"].get(dataset_id)
            if record is None or record["step_id"] != result["step_id"]:
                raise ValueError("步骤引用的数据集不存在或来源步骤不匹配")
    return {"analysis_result": {"datasets": state["datasets"], "step_results": results}}


def build_analysis_execution_graph(*, chat=False):
    graph = StateGraph(AnalysisExecutionState, context_schema=AgentContext,
                       input_schema=AnalysisExecutionInput, output_schema=AnalysisExecutionOutput)
    graph.add_node("initialize_subgraph", initialize_subgraph)
    graph.add_node("load_step", load_step)
    if chat:
        from life_insurance_business_analysis_assistant.agent.chat import track_analysis_step
        graph.add_node("fetch_step_data", track_analysis_step("fetch_step_data", fetch_step_data))
        graph.add_node("analyze_step", track_analysis_step("analyze_step", analyze_step))
    else:
        graph.add_node("fetch_step_data", fetch_step_data)
        graph.add_node("analyze_step", analyze_step)
    graph.add_node("finalize_subgraph", finalize_subgraph)
    graph.add_edge(START, "initialize_subgraph")
    graph.add_edge("initialize_subgraph", "load_step")
    graph.add_conditional_edges("load_step", route_current_step)
    graph.add_edge("fetch_step_data", "analyze_step")
    graph.add_conditional_edges("analyze_step", route_analysis)
    graph.add_edge("finalize_subgraph", END)
    return graph.compile()
