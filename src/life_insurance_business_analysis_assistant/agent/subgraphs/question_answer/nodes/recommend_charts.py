from langchain_core.runnables import RunnableConfig
from life_insurance_business_analysis_assistant.agent.shared.messages import AnalysisStream, chat_message
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.state import AgentState
from life_insurance_business_analysis_assistant.agent.shared.charts import generate_chart_recommendations


def recommend_charts(state: AgentState, config: RunnableConfig) -> dict:
    """智能问答展示适配；报告直接使用无聊天消息的图表决策函数。"""
    progress = AnalysisStream(state, "charts", "图表推荐", protocol=False) if state.get("analysis_id") else None
    update = generate_chart_recommendations(state, config, progress)
    if progress:
        update["messages"] = [chat_message(state, "charts", "### 图表推荐\n\n",
                                           reasoning="".join(progress.reasoning))]
    return update
