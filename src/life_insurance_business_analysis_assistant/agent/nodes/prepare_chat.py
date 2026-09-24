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
    fresh = isinstance(latest, HumanMessage) and latest.id != state.get("analysis_id") # 判断是不是最新的用户问题: 1.最新消息来自用户;2.最新消息id不能是状态中的id

    question = state.get("question") # Chat UI可以不提交question，而只提交messages
    if question is not None and not isinstance(question, str):
        raise ValueError("question 必须为文本")
    # 后端当前支持两种输入方式：1.提交messages；2.提交question
    
    if fresh: # 新消息
        text = message_text(latest) # 把消息内容规范化为字符串
        # question 属于持久业务状态；旧值不能覆盖本轮刚提交的消息。
        if question is not None and question != state.get("last_question") and question.strip() != text: # State是持久化的，避免Studio和ChatUI混用
            raise ValueError("question 与用户消息不一致，请只提交一种输入")
        human = latest
    else: 
        if not isinstance(question, str) or not question.strip():
            raise ValueError("请提交 question 或一条新的用户消息")
        text = question.strip() # 用户通过Studio提交question
        human = HumanMessage(content=text, id=str(uuid4()))
    return {
        **create_initial_state(text),  # 重置State，短生命周期，单次分析任务
        "messages": [human], # 消息列表累加，长生命周期，整个Thread
        "analysis_id": human.id, # 分析任务ID，用于区分同一个Chat Thread中不同分析任务
        "last_question": text, # 服务于下一次进入prepare_chat时的判断，属于聊天入口控制字段
        "status": "正在匹配场景",# 下一步状态
    }
