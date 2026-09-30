from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.nodes.load_report_template import load_report_template
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.state import ReportState, ReportOutput
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.presentation import track_report_node
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.nodes.initialize_report import initialize_report
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.nodes.analyze_report_step import analyze_report_step
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.nodes.commit_report_step import commit_report_step
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.nodes.recommend_report_charts import recommend_report_charts
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.nodes.finalize_report import finalize_report
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.nodes.load_report_step import load_report_step
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.nodes.fetch_report_step_data import fetch_report_step_data


def build_report_graph(*, studio_context: AgentContext):
    graph = StateGraph(ReportState, context_schema=AgentContext, input_schema=ReportOutput, output_schema=ReportOutput)
    for name, label, node in (
        ("load_report_template", "加载报告模板", lambda state, config: load_report_template(state, Runtime(context=studio_context))),
        ("initialize_report", "建立报告章节", lambda state, config: initialize_report(state)),
        ("load_report_step", "加载分析步骤", lambda state, config: load_report_step(state)),
        ("fetch_report_step_data", "查询数据", lambda state, config: fetch_report_step_data(state, Runtime(context=studio_context))),
        ("analyze_report_step", "生成章节正文", analyze_report_step),
        ("commit_report_step", "保存章节结果", lambda state, config: commit_report_step(state)),
        ("recommend_report_charts", "生成章节图表", recommend_report_charts),
        ("finalize_report", "完成报告", lambda state, config: finalize_report(state)),
    ):
        graph.add_node(name, track_report_node(name, label, node))
    graph.add_edge(START, "load_report_template")
    graph.add_edge("load_report_template", "initialize_report")
    graph.add_edge("initialize_report", "load_report_step")
    graph.add_conditional_edges("load_report_step",
        lambda state: "fetch_report_step_data" if state["current_step"]["metrics"] else "analyze_report_step",
        ["fetch_report_step_data", "analyze_report_step"])
    graph.add_edge("fetch_report_step_data", "analyze_report_step")
    graph.add_edge("analyze_report_step", "commit_report_step")
    graph.add_conditional_edges("commit_report_step",
        lambda state: "load_report_step" if state["step_index"] < len(state["template"]["steps"]) else "recommend_report_charts",
        ["load_report_step", "recommend_report_charts"])
    graph.add_edge("recommend_report_charts", "finalize_report")
    graph.add_edge("finalize_report", END)
    return graph.compile()
