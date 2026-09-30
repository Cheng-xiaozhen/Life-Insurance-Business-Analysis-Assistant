"""聊天父图：初始化请求，并路由到所属业务子图。"""

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.state import ChatState, StudioInput
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.graph import build_question_answer_graph
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.graph import build_report_graph
from life_insurance_business_analysis_assistant.agent.nodes.prepare_request import prepare_request


def build_chat_graph(*, studio_context: AgentContext):
    """入口父图只初始化本轮任务并选择业务子图。"""
    graph = StateGraph(ChatState, context_schema=AgentContext, input_schema=StudioInput)
    graph.add_node("prepare_request", prepare_request)
    graph.add_node("question_answer", build_question_answer_graph(studio_context=studio_context))
    report_graph = build_report_graph(studio_context=studio_context)

    def run_report(state: ChatState, config: RunnableConfig):
        # ponytail: 最多 1000 个图步；超大模板需要显式增加 recursion_limit。
        return report_graph.invoke(state, {**config, "recursion_limit": max(config.get("recursion_limit", 25), 1000)})

    graph.add_node("report_generation", run_report)
    graph.add_edge(START, "prepare_request")
    graph.add_conditional_edges("prepare_request",
        lambda state: "report_generation" if state.get("report_id") else "question_answer",
        ["report_generation", "question_answer"])
    graph.add_edge("question_answer", END)
    graph.add_edge("report_generation", END)
    return graph.compile()
