"""呈现完整图表推荐并结束本次分析。"""

from langgraph.config import get_stream_writer

from life_insurance_business_analysis_assistant.agent.chat import chat_message
from life_insurance_business_analysis_assistant.agent.state import ChatState


def present_charts(state: ChatState):
    decisions = state["chart_recommendations"]
    sections = []
    for decision in decisions:
        title = "图表推荐" if decision["recommended"] else "不推荐图表"
        text = f"#### {title} · 步骤 {decision['step_id']}\n\n{decision['reason']}\n\n{decision['description']}"
        if decision["recommended"]:
            text += f"\n\n图表类型：{decision['chart_type']}；维度：{'、'.join(decision['dimensions'])}；指标：{'、'.join(decision['metrics'])}。"
        sections.append(text)
    text = "### 图表推荐\n\n" + "\n\n".join(sections)
    previous = next((m for m in reversed(state.get("messages", [])) if m.id == f"{state['analysis_id']}:charts"), None)
    reasoning = previous.additional_kwargs.get("reasoning", "") if previous else ""
    get_stream_writer()({"type": "analysis_delta", "id": f"{state['analysis_id']}:charts",
                         "analysis_id": state["analysis_id"], "start": True, "text": text, "reasoning": reasoning, "status": "已完成"})
    return {"messages": [chat_message(state, "charts", text, reasoning=reasoning, charts=decisions)], "status": "已完成"}
