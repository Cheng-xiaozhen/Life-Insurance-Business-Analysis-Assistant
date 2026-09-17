"""暂停工作流，接收场景选择或槽位补充回答。"""

from typing import TypedDict

from langgraph.types import interrupt

from life_insurance_business_analysis_assistant.agent.state import AgentState


class ClarifyUpdate(TypedDict):
    """选择成功后写入场景编码并清空追问。"""

    scenario_id: str
    clarification: None


class SlotReplyUpdate(TypedDict):
    """保留追问上下文，只把新回答交给槽位解析节点。"""

    user_reply: str


def clarify(state: AgentState) -> ClarifyUpdate | SlotReplyUpdate:
    """按追问类型接收场景编码或槽位补充文本。"""
    clarification = state["clarification"]
    # 进入槽位补充追问
    if clarification and clarification["kind"] == "slot_completion":
        prompt = clarification["prompt"]
        while True:
            reply = interrupt({"kind": "slot_completion", "prompt": prompt,
                               "slot_issues": clarification["slot_issues"]})
            if isinstance(reply, str) and reply.strip():
                return SlotReplyUpdate(user_reply=reply)
            prompt = "请用非空文本补充参数。"
    if clarification is None or clarification["kind"] != "scenario_selection":
        raise ValueError("clarify 需要有效的追问类型")
    # 进入场景选择追问
    candidates = state["candidates"]
    if len(candidates) < 2:
        raise ValueError("场景选择追问需要至少两个候选")
    valid_ids = {candidate["scenario_id"] for candidate in candidates}
    prompt = clarification["prompt"]
    while True:
        # 恢复时节点从头执行；保持 interrupt 顺序稳定，不在此处修改 State。
        reply = interrupt({
            "kind": clarification["kind"],
            "prompt": prompt,
            "candidates": candidates,
        })
        if isinstance(reply, str) and reply in valid_ids:
            return ClarifyUpdate(scenario_id=reply, clarification=None)
        prompt = "选择无效，请提交本次候选中的场景编码。"
