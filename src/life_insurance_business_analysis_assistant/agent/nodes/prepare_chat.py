"""校验聊天输入并初始化本次分析。"""

from uuid import uuid4

from langchain_core.messages import HumanMessage

from life_insurance_business_analysis_assistant.agent.state import ChatState, create_initial_state


def message_text(message: HumanMessage) -> str:
    content = message.content
    if isinstance(content, str):
        text = content
    else:
        if any(not isinstance(block, dict) or block.get("type") != "text" or not isinstance(block.get("text"), str) for block in content):
            raise ValueError("当前分析仅支持文本，请移除图片或附件")
        text = "\n".join(block.get("text", "") for block in content)
    if not text.strip():
        raise ValueError("请输入非空的分析问题")
    return text.strip()


def prepare_chat(state: ChatState):
    messages = state.get("messages", []) # 取当前线程已经累计的messages
    latest = messages[-1] if messages else None # 取最后一条message
    fresh = isinstance(latest, HumanMessage) and latest.id != state.get("analysis_id") # 判断是不是新消息，1.最新消息来自用户;2.
    question = state.get("question")
    if question is not None and not isinstance(question, str):
        raise ValueError("question 必须为文本")
    # 后端当前支持两种输入方式：1.提交messages；2.提交question
    if fresh:
        text = message_text(latest)
        # question 属于持久业务状态；旧值不能覆盖本轮刚提交的消息。
        if question is not None and question != state.get("last_question") and question.strip() != text:
            raise ValueError("question 与用户消息不一致，请只提交一种输入")
        human = latest
    else:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("请提交 question 或一条新的用户消息")
        text = question.strip()
        human = HumanMessage(content=text, id=str(uuid4()))
    return {
        **create_initial_state(text), "messages": [human], "analysis_id": human.id,
        "last_question": text, "status": "正在匹配场景",
    }
