"""智能问答前半段：匹配、选择场景、加载模板和补齐槽位。"""

from typing import Literal

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
from life_insurance_business_analysis_assistant.agent.state import AgentState
from life_insurance_business_analysis_assistant.agent.chat import (
    ChatState, StudioInput, chart_message, no_match, prepare_chat, present_clarification, track_execution,
)


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


def build_graph(*, studio_context: AgentContext | None = None):
    """
    创建分析图
    studio_context 是一个可选的运行上下文，根据是否提供该参数，函数支持两种构建方式：
    1. 不提供 studio_context：创建一个普通分析图，不支持聊天能力。
    2. 提供 studio_context：创建一个支持聊天能力的分析图

    """
    graph = StateGraph(ChatState if studio_context is not None else AgentState, context_schema=AgentContext if studio_context is None else None,
                       input_schema=StudioInput if studio_context is not None else AgentState)
    node_state = ChatState if studio_context is not None else AgentState
    for name, node in (("match_scenario", match_scenario), ("load_template", load_template),
                       ("fetch_step_data", fetch_step_data)):
        graph.add_node(name, node if studio_context is None else track_execution(
            name, lambda state, config, node=node: node(state, Runtime(context=studio_context))), input_schema=node_state)
    graph.add_node("resolve_slots", resolve_slots if studio_context is None else track_execution(
        "resolve_slots", lambda state, config: resolve_slots(state)), input_schema=node_state)
    for name, node in (("analyze_step", analyze_step),
                       ("summarize_scenario", summarize_scenario), ("recommend_charts", recommend_charts)):
        graph.add_node(name, node if studio_context is None else track_execution(name, node), input_schema=node_state)
    graph.add_node("clarify", clarify if studio_context is None else track_execution(
        "clarify", lambda state, config: clarify(state)), input_schema=node_state)
    if studio_context is not None:
        graph.add_node("prepare_chat", prepare_chat)
        for name, node in (("present_clarification", present_clarification), ("no_match", no_match),
                           ("present_charts", chart_message)):
            graph.add_node(name, track_execution(name, lambda state, config, node=node: node(state)))
        graph.add_edge(START, "prepare_chat")
        graph.add_edge("prepare_chat", "match_scenario")
        graph.add_edge("present_clarification", "clarify")
        graph.add_edge("no_match", END)
        graph.add_edge("present_charts", END)
    else:
        graph.add_edge(START, "match_scenario")
    clarify_target = "present_clarification" if studio_context is not None else "clarify"
    graph.add_conditional_edges("match_scenario", route_match, {
        "no_match": "no_match" if studio_context is not None else END,
        "single_match": "load_template",
        "multiple_matches": clarify_target,
    })
    graph.add_conditional_edges("clarify", route_clarify)
    graph.add_edge("load_template", "resolve_slots")
    graph.add_conditional_edges("resolve_slots", route_slots, {"clarify": clarify_target, "complete": "fetch_step_data"})
    graph.add_edge("fetch_step_data", "analyze_step")
    graph.add_conditional_edges("analyze_step", route_analysis, {
        "fetch_step_data": "fetch_step_data", "complete": "summarize_scenario",
    })
    graph.add_edge("summarize_scenario", "recommend_charts")
    graph.add_edge("recommend_charts", "present_charts" if studio_context is not None else END)
    # ponytail: POC 状态仅存内存，需要跨进程恢复时换持久化 checkpointer。
    # Studio 的检查点由 Agent Server 提供，不能额外创建本地 saver。
    return graph.compile(checkpointer=InMemorySaver() if studio_context is None else None)
