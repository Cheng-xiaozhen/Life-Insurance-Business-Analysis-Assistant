"""将当前追问呈现为聊天消息。"""

from life_insurance_business_analysis_assistant.agent.chat import chat_message
from life_insurance_business_analysis_assistant.agent.state import ChatState


def present_clarification(state: ChatState):
    clarification = state["clarification"]
    # 每次补参使用最新已提交的回复 ID，重复执行同一节点仍覆盖同一条消息。
    latest = state["messages"][-1].id
    return {"messages": [chat_message(state, f"clarify:{latest}", clarification["prompt"])],
            "status": "等待补充信息"}
