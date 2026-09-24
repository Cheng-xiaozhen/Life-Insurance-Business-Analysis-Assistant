"""将当前追问呈现为聊天消息。"""

from life_insurance_business_analysis_assistant.agent.chat import chat_message
from life_insurance_business_analysis_assistant.agent.state import ChatState


def present_clarification(state: ChatState):
    """
    纯粹的Chat UI展示节点，负责把业务节点的Clarification转化为聊天消息，供前端展示。
    """
    clarification = state["clarification"]
    latest_message_id = state["messages"][-1].id # 拿到当前聊天记录中最新一条消息的ID
    return {"messages": [chat_message(state, f"clarify:{latest_message_id}", clarification["prompt"])],
            "status": "等待补充信息"}
