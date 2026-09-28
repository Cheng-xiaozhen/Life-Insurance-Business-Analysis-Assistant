"""单入口、单出口的分析循环；继承父图 checkpointer。"""
from typing import Literal

from langgraph.graph import END, START, StateGraph

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.nodes.analyze_step import analyze_step
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.nodes.fetch_step_data import fetch_step_data
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.nodes.initialize_subgraph import initialize_subgraph
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.nodes.load_step import load_step
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.nodes.finalize_subgraph import finalize_subgraph
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.state import AnalysisExecutionInput, AnalysisExecutionOutput, AnalysisExecutionState


def route_current_step(state: AnalysisExecutionState) -> Literal["fetch_step_data", "analyze_step"]:
    return "fetch_step_data" if state["current_step"]["metrics"] else "analyze_step"


def route_analysis(state: AnalysisExecutionState) -> Literal["load_step", "finalize_subgraph"]:
    index, count = state["step_index"], len(state["template"]["steps"])
    if type(index) is not int or not 0 <= index <= count:
        raise ValueError("分析后的 step_index 超出模板范围")
    return "load_step" if index < count else "finalize_subgraph"


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
