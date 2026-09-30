from langchain_core.runnables import RunnableConfig
from life_insurance_business_analysis_assistant.agent.shared.charts import generate_chart_recommendations
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.presentation import publish_report
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.state import ReportState
from life_insurance_business_analysis_assistant.agent.shared.execution import finalize_execution


def recommend_report_charts(state: ReportState, config: RunnableConfig):
    finalize_execution(state)
    # 共用图表决策能力，不创建智能问答的图表占位消息。
    update = generate_chart_recommendations(state, config)
    return {**update, **publish_report({**state, **update}, charts_ready=True)}
