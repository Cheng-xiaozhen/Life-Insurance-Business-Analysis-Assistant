"""暂停工作流"""

from typing import TypedDict

from langgraph.types import interrupt
from langchain_core.messages import HumanMessage

from life_insurance_business_analysis_assistant.agent.state import AgentState


class ClarifyUpdate(TypedDict):
    """
    场景确认，选择成功后写入场景编码并清空追问。
    """
    scenario_id: str
    clarification: None


def clarify(state: AgentState) -> ClarifyUpdate:
    """等待场景选择；步骤执行不再发起查询参数澄清。"""
    clarification = state["clarification"]
    if clarification is None or clarification["kind"] != "scenario_selection":
        raise ValueError("clarify 需要有效的追问类型")
    
    # 进入场景选择追问
    candidates = state["candidates"]
    if not candidates:
        raise ValueError("场景确认需要至少一个候选")
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
            update = ClarifyUpdate(scenario_id=reply, clarification=None) # 清空clarification，用于后续节点判断
            if state.get("analysis_id"): # 判断是不是Chat Graph
                name = next(item["name"] for item in candidates if item["scenario_id"] == reply)
                update.update(
                    messages=[HumanMessage(content=f"选择场景：{name}", id=f"{state['messages'][-1].id}:reply")],
                    status="正在加载分析模板"
                    ) # Chat模式下追加HumanMessage
            return update
        prompt = "选择无效，请提交本次候选中的场景编码。"
