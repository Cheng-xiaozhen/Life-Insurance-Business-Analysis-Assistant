"""模板驱动的智能问答：确认、补参、规划/取数/分析循环、总结和图表。"""

from typing import Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.nodes.analyze_step import analyze_step
from life_insurance_business_analysis_assistant.agent.nodes.clarify import clarify
from life_insurance_business_analysis_assistant.agent.nodes.fetch_step_data import fetch_step_data
from life_insurance_business_analysis_assistant.agent.nodes.plan_step import plan_step
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.nodes.match_scenario import match_scenario
from life_insurance_business_analysis_assistant.agent.nodes.summarize_scenario import summarize_scenario
from life_insurance_business_analysis_assistant.agent.nodes.recommend_charts import recommend_charts
from life_insurance_business_analysis_assistant.agent.state import AgentState, ChatState, StudioInput
from life_insurance_business_analysis_assistant.data_coverage import pending_queries
from life_insurance_business_analysis_assistant.agent.chat import track_execution
from life_insurance_business_analysis_assistant.agent.nodes.no_match import no_match
from life_insurance_business_analysis_assistant.agent.nodes.prepare_chat import prepare_chat
from life_insurance_business_analysis_assistant.agent.nodes.present_clarification import present_clarification
from life_insurance_business_analysis_assistant.agent.nodes.present_charts import present_charts


def route_match(state: AgentState) -> Literal["no_match", "confirm"]:
    """
    判断场景匹配结果，如果没有匹配到候选场景，则返回 "no_match"；如果匹配到了候选场景，则返回 "confirm"。
    """
    return "confirm" if state["candidates"] else "no_match"


def route_clarify(state: AgentState) -> Literal["load_template", "plan_step"]:
    clarification = state["clarification"]
    if clarification is None:
        return "load_template"
    if clarification["kind"] != "step_clarification":
        raise ValueError("场景确认后仅支持步骤澄清")
    return "plan_step"


def route_analysis(state: AgentState) -> Literal["plan_step", "complete"]:
    """分析成功后索引已加一；等于步骤总数时才结束。"""
    template, index = state["template"], state["step_index"]
    if template is None or type(index) is not int or not 0 <= index <= len(template["steps"]):
        raise ValueError("分析后的 step_index 超出模板范围")
    return "plan_step" if index < len(template["steps"]) else "complete"


def route_plan(state: AgentState) -> Literal["clarify", "fetch_step_data", "analyze_step"]:
    if state["clarification"]:
        return "clarify"
    return route_fetch(state)


def route_fetch(state: AgentState) -> Literal["fetch_step_data", "analyze_step"]:
    return "fetch_step_data" if pending_queries(state) else "analyze_step"


def build_analysis_graph():
    """创建普通分析图：调用时通过 context 传入 AgentContext。"""
    graph = StateGraph(AgentState, context_schema=AgentContext, input_schema=AgentState)
    for name, node in (("match_scenario", match_scenario), ("load_template", load_template),
                       ("clarify", clarify),
                       ("plan_step", plan_step), ("fetch_step_data", fetch_step_data),
                       ("analyze_step", analyze_step), ("summarize_scenario", summarize_scenario),
                       ("recommend_charts", recommend_charts)):
        graph.add_node(name, node, input_schema=AgentState)
    graph.add_edge(START, "match_scenario")
    _add_analysis_edges(graph, clarify_target="clarify", no_match_target=END, charts_target=END)
    # ponytail: POC 状态仅存内存，需要跨进程恢复时换持久化 checkpointer。
    return graph.compile(checkpointer=InMemorySaver())


def build_chat_graph(*, studio_context: AgentContext):
    """创建聊天图：构建时绑定上下文，接受 StudioInput，维护 ChatState。"""
    graph = StateGraph(ChatState, input_schema=StudioInput) # ChatAgent内部完整状态；StudioInput外部输入，可以提交question或messages
    for name, node in (("match_scenario",  match_scenario), ("load_template", load_template),
                       ("fetch_step_data", fetch_step_data), ("plan_step", plan_step)):
        graph.add_node(name, track_execution(
            name, lambda state, config, node=node: node(state, Runtime(context=studio_context))),
            input_schema=ChatState)
        
    graph.add_node("clarify", track_execution("clarify", lambda state, config: clarify(state)),
                   input_schema=ChatState)
        
    for name, node in (("analyze_step", analyze_step),
                       ("summarize_scenario", summarize_scenario), ("recommend_charts", recommend_charts)):
        graph.add_node(name, track_execution(name, node), input_schema=ChatState)
        
    graph.add_node("prepare_chat", prepare_chat)
    for name, node in (("present_clarification", present_clarification), ("no_match", no_match),
                       ("present_charts", present_charts)):
        graph.add_node(name, track_execution(name, lambda state, config, node=node: node(state)))
    graph.add_edge(START, "prepare_chat")
    graph.add_edge("prepare_chat", "match_scenario")
    graph.add_edge("present_clarification", "clarify")
    graph.add_edge("no_match", END)
    graph.add_edge("present_charts", END)
    _add_analysis_edges(graph, clarify_target="present_clarification",
                        no_match_target="no_match", charts_target="present_charts")
    # Studio 的检查点由 Agent Server 提供，不能额外创建本地 saver。
    return graph.compile()


def _add_analysis_edges(graph: StateGraph, *, clarify_target: str, no_match_target: str, charts_target: str):
    """两种入口共用业务路线，追问和结束位置由各入口指定。"""
    graph.add_conditional_edges("match_scenario", route_match, {
        "no_match": no_match_target,
        "confirm": clarify_target,
    })
    graph.add_conditional_edges("clarify", route_clarify)
    graph.add_edge("load_template", "plan_step")
    graph.add_conditional_edges("plan_step", route_plan, {
        "clarify": clarify_target, "fetch_step_data": "fetch_step_data", "analyze_step": "analyze_step",
    })
    graph.add_conditional_edges("fetch_step_data", route_fetch)
    graph.add_conditional_edges("analyze_step", route_analysis, {
        "plan_step": "plan_step", "complete": "summarize_scenario",
    })
    graph.add_edge("summarize_scenario", "recommend_charts")
    graph.add_edge("recommend_charts", charts_target)
