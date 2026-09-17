"""智能问答前半段：匹配、选择场景、加载模板和补齐槽位。"""

from typing import Literal
from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.nodes.analyze_step import analyze_step
from life_insurance_business_analysis_assistant.agent.nodes.clarify import clarify
from life_insurance_business_analysis_assistant.agent.nodes.fetch_step_data import fetch_step_data
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.nodes.match_scenario import match_scenario
from life_insurance_business_analysis_assistant.agent.nodes.resolve_slots import resolve_slots
from life_insurance_business_analysis_assistant.agent.nodes.summarize_scenario import summarize_scenario
from life_insurance_business_analysis_assistant.agent.nodes.recommend_charts import recommend_charts
from life_insurance_business_analysis_assistant.agent.state import AgentState, create_initial_state


def route_match(state: AgentState) -> Literal["no_match", "single_match", "multiple_matches"]:
    """仅按候选数量路由，多命中不根据分数自动选择。"""
    count = len(state["candidates"])
    if count == 0:
        return "no_match"
    return "single_match" if count == 1 else "multiple_matches"


def route_clarify(state: AgentState) -> Literal["load_template", "resolve_slots"]:
    """槽位回复保留追问类型；场景选择成功已清空追问。"""
    return "resolve_slots" if state["clarification"] is not None else "load_template"


def route_slots(state: AgentState) -> Literal["clarify", "complete"]:
    return "clarify" if state["clarification"] is not None else "complete"


def route_analysis(state: AgentState) -> Literal["fetch_step_data", "complete"]:
    """分析成功后索引已加一；等于步骤总数时才结束。"""
    template, index = state["template"], state["step_index"]
    if template is None or type(index) is not int or not 0 <= index <= len(template["steps"]):
        raise ValueError("分析后的 step_index 超出模板范围")
    return "fetch_step_data" if index < len(template["steps"]) else "complete"


class StudioInput(TypedDict):
    question: str  # Studio 每次新分析只输入原始问题。


def build_graph(*, studio_context: AgentContext | None = None):
    """创建 POC 图；调用方复用此实例，并用相同 thread_id 恢复暂停。"""
    graph = StateGraph(AgentState, context_schema=AgentContext if studio_context is None else None,
                       input_schema=StudioInput if studio_context is not None else AgentState)
    def start_studio(state: AgentState):
        initial = create_initial_state(state["question"])
        return {**initial, **match_scenario(initial, Runtime(context=studio_context))}

    graph.add_node("match_scenario", match_scenario if studio_context is None else start_studio)
    graph.add_node("clarify", clarify)
    graph.add_node("load_template", load_template if studio_context is None else
                   lambda state: load_template(state, Runtime(context=studio_context)))
    graph.add_node("resolve_slots", resolve_slots)
    graph.add_node("fetch_step_data", fetch_step_data if studio_context is None else
                   lambda state: fetch_step_data(state, Runtime(context=studio_context)))
    graph.add_node("analyze_step", analyze_step)
    graph.add_node("summarize_scenario", summarize_scenario)
    graph.add_node("recommend_charts", recommend_charts)
    graph.add_edge(START, "match_scenario")
    graph.add_conditional_edges("match_scenario", route_match, {
        "no_match": END,
        "single_match": "load_template",
        "multiple_matches": "clarify",
    })
    graph.add_conditional_edges("clarify", route_clarify)
    graph.add_edge("load_template", "resolve_slots")
    graph.add_conditional_edges("resolve_slots", route_slots, {"clarify": "clarify", "complete": "fetch_step_data"})
    graph.add_edge("fetch_step_data", "analyze_step")
    graph.add_conditional_edges("analyze_step", route_analysis, {
        "fetch_step_data": "fetch_step_data", "complete": "summarize_scenario",
    })
    graph.add_edge("summarize_scenario", "recommend_charts")
    graph.add_edge("recommend_charts", END)
    # ponytail: POC 状态仅存内存，需要跨进程恢复时换持久化 checkpointer。
    # Studio 的检查点由 Agent Server 提供，不能额外创建本地 saver。
    return graph.compile(checkpointer=InMemorySaver() if studio_context is None else None)
