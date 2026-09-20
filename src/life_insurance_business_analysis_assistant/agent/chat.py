"""Agent Server 的聊天边界；业务节点仍只读取本次分析状态。"""

from typing import Annotated, NotRequired
from uuid import uuid4

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph.message import add_messages
from langgraph.config import get_stream_writer
from langgraph.constants import TAG_NOSTREAM
from langchain_core.runnables.config import merge_configs
from typing_extensions import TypedDict

from life_insurance_business_analysis_assistant.agent.state import AgentState, create_initial_state


class ChatState(AgentState):
    messages: Annotated[list[AnyMessage], add_messages]
    analysis_id: str
    last_question: str
    status: str


class StudioInput(TypedDict):
    question: NotRequired[str | None]
    messages: NotRequired[Annotated[list[AnyMessage], add_messages]]


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
    messages = state.get("messages", [])
    latest = messages[-1] if messages else None
    fresh = isinstance(latest, HumanMessage) and latest.id != state.get("analysis_id")
    question = state.get("question")
    if question is not None and not isinstance(question, str):
        raise ValueError("question 必须为文本")
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


def chat_message(state: ChatState, suffix: str, text: str, **metadata):
    # reducer 将字典转换为 AIMessage；最终文本仅经 values 发布，避免与 custom 流重复追加。
    return {"type": "ai", "content": text, "id": f"{state['analysis_id']}:{suffix}",
            "additional_kwargs": {"analysis": True, **metadata}}


def present_clarification(state: ChatState):
    clarification = state["clarification"]
    # 每次补参使用最新已提交的回复 ID，重复执行同一节点仍覆盖同一条消息。
    latest = state["messages"][-1].id
    return {"messages": [chat_message(state, f"clarify:{latest}", clarification["prompt"])],
            "status": "等待补充信息"}


def no_match(state: ChatState):
    return {"messages": [chat_message(state, "no-match", "未匹配到分析场景。请明确要分析的指标，例如标保或价值，并提供年份和月份。")],
            "status": "已完成"}


def chart_message(state: ChatState):
    decision = state["chart_recommendations"][0]
    title = "图表推荐" if decision["recommended"] else "本次不推荐图表"
    text = f"### {title}\n\n{decision['reason']}\n\n{decision['description']}"
    if decision["recommended"]:
        text += f"\n\n图表类型：{decision['chart_type']}；维度：{'、'.join(decision['dimensions'])}；指标：{'、'.join(decision['metrics'])}。"
    return {"messages": [chat_message(state, "charts", text)], "status": "已完成"}


def stream_text(llm, prompt, config, state, suffix, heading):
    """聊天流使用固定消息 ID；完整文本通过节点返回值提交检查点。"""
    chatting = bool(state.get("analysis_id"))
    writer = get_stream_writer() if chatting else None
    if chatting:
        config = merge_configs(config, {"tags": [TAG_NOSTREAM]})
    stream = llm.stream_events(prompt, config=config, version="v3")
    parts = []
    if writer:
        writer({"type": "analysis_delta", "id": f"{state['analysis_id']}:{suffix}",
                "text": f"### {heading}\n\n", "start": True, "status": heading})
    for text in stream.text:
        parts.append(text)
        if writer:
            writer({"type": "analysis_delta", "id": f"{state['analysis_id']}:{suffix}", "text": text})
    return "".join(parts).strip(), stream.output
