"""呈现未匹配到分析场景的结果。"""

from life_insurance_business_analysis_assistant.agent.shared.messages import chat_message
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.state import QuestionAnswerState


def no_match(state: QuestionAnswerState):
    return {"messages": [chat_message(state, "no-match", "未匹配到分析场景。请明确要分析的指标，例如标保或价值，并提供年份和月份。")],
            "status": "已完成"}
