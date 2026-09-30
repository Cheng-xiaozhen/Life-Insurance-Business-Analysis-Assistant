"""模板驱动的智能问答：确认、确定性取数/分析循环、总结和图表。"""

from typing import Literal
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.subgraphs.analysis_execution.graph import build_analysis_execution_graph
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.subgraphs.analysis_execution.state import AnalysisExecutionInput
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.nodes.clarify import clarify
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.nodes.match_scenario import match_scenario
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.nodes.summarize_scenario import summarize_scenario
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.nodes.recommend_charts import recommend_charts
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.state import AgentState
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.state import QuestionAnswerState
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.presentation import track_execution, chat_analysis_execution
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.nodes.no_match import no_match
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.nodes.present_clarification import present_clarification
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.nodes.present_charts import present_charts


def route_match(state: AgentState) -> Literal["no_match", "confirm"]:
    """
    判断场景匹配结果，如果没有匹配到候选场景，则返回 "no_match"；如果匹配到了候选场景，则返回 "confirm"。
    """
    return "confirm" if state["candidates"] else "no_match"


def route_clarify(state: AgentState) -> Literal["load_template"]:
    if state["clarification"] is not None:
        raise ValueError("场景确认尚未完成")
    return "load_template"


def build_analysis_graph():
    """创建普通分析图：调用时通过 context 传入 AgentContext。"""
    graph = StateGraph(AgentState, context_schema=AgentContext, input_schema=AgentState)
    for name, node in (("match_scenario", match_scenario), ("load_template", load_template),
                       ("clarify", clarify),
                       ("summarize_scenario", summarize_scenario),
                       ("recommend_charts", recommend_charts)):
        graph.add_node(name, node, input_schema=AgentState)
    graph.add_node("analysis_execution", build_analysis_execution_graph(), input_schema=AnalysisExecutionInput)
    graph.add_edge(START, "match_scenario")
    _add_analysis_edges(graph, clarify_target="clarify", no_match_target=END, charts_target=END)
    # ponytail: POC 状态仅存内存，需要跨进程恢复时换持久化 checkpointer。
    return graph.compile(checkpointer=InMemorySaver())


def build_question_answer_graph(*, studio_context: AgentContext):
    """智能问答业务子图；内部继续使用 analysis_execution 子图。"""
    graph = StateGraph(QuestionAnswerState, context_schema=AgentContext)
    for name, node in (("match_scenario",  match_scenario), ("load_template", load_template)):
        graph.add_node(name, track_execution(
            name, lambda state, config, node=node: node(state, Runtime(context=studio_context))),
            input_schema=QuestionAnswerState)
        
    graph.add_node("clarify", track_execution("clarify", lambda state, config: clarify(state)),
                   input_schema=QuestionAnswerState)
        
    graph.add_node("analysis_execution", chat_analysis_execution(
        build_analysis_execution_graph(chat=True), studio_context), input_schema=QuestionAnswerState)
    
    for name, node in (("summarize_scenario", summarize_scenario), ("recommend_charts", recommend_charts)):
        graph.add_node(name, track_execution(name, node), input_schema=QuestionAnswerState)
        
    for name, node in (("present_clarification", present_clarification), ("no_match", no_match),
                       ("present_charts", present_charts)):
        graph.add_node(name, track_execution(name, lambda state, config, node=node: node(state)))
    graph.add_edge(START, "match_scenario")
    graph.add_edge("present_clarification", "clarify")
    graph.add_edge("no_match", END)
    graph.add_edge("present_charts", END)
    _add_analysis_edges(graph, clarify_target="present_clarification",
                        no_match_target="no_match", charts_target="present_charts")
    return graph.compile()


def _add_analysis_edges(graph: StateGraph, *, clarify_target: str, no_match_target: str, charts_target: str):
    """两种入口共用业务路线，追问和结束位置由各入口指定。"""
    graph.add_conditional_edges("match_scenario", route_match, {
        "no_match": no_match_target,
        "confirm": clarify_target,
    })
    graph.add_conditional_edges("clarify", route_clarify)
    graph.add_edge("load_template", "analysis_execution")
    graph.add_edge("analysis_execution", "summarize_scenario")
    graph.add_edge("summarize_scenario", "recommend_charts")
    graph.add_edge("recommend_charts", charts_target)
