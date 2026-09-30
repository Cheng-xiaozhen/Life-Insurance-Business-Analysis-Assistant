import logging
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphInterrupt
from langgraph.runtime import Runtime
from life_insurance_business_analysis_assistant.agent.context import AgentContext
from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer
from langchain_core.runnables.config import merge_configs
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.state import QuestionAnswerState
from life_insurance_business_analysis_assistant.agent.shared.messages import chat_message


logger = logging.getLogger(__name__)

def track_execution(name, node):
    """聊天边界统一记录节点进度；成功记录写入检查点，失败仍保留原重试语义。"""
    def run(state: QuestionAnswerState, config: RunnableConfig):
        analysis_id = state["analysis_id"]
        index = state.get("step_index", 0)
        template = state.get("template")
        step = template["steps"][index] if template and index < len(template["steps"]) else None
        labels = {
            "match_scenario": "识别分析场景", "load_template": "加载分析方案",
            "present_clarification": "请求补充信息",
            "clarify": "等待补充信息", "no_match": "未匹配到分析场景",
            "fetch_step_data": "查询数据", "analyze_step": "生成步骤分析",
            "summarize_scenario": "生成场景总结", "recommend_charts": "生成图表推荐",
            "present_charts": "分析报告已完成",
        }
        label = labels[name]
        suffix = None
        if name in ("fetch_step_data", "analyze_step") and step:
            label += f" · 步骤 {step['step_id']}：{step['text']}"
            if name == "analyze_step":
                suffix = f"step:{step['step_id']}"
        elif name == "summarize_scenario":
            suffix = "summary"
        elif name == "recommend_charts":
            suffix = "charts"
        turn = state.get("turn_id") or next((m.id for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)), analysis_id)
        entry_id = f"{analysis_id}:{name}:{index}:{turn}"
        if name == "fetch_step_data" and step:
            label += " · " + "、".join(step["metrics"])
        entry = {"id": entry_id, "analysis_id": analysis_id, "label": label, "state": "running"}
        if suffix:
            entry["message_id"] = f"{analysis_id}:{suffix}"
        writer = get_stream_writer()
        writer({"type": "analysis_progress", "entry": entry})
        logger.info("analysis_id=%s node=%s step_index=%s started", analysis_id, name, index)
        try:
            update = node(state, config)
        except GraphInterrupt:
            writer({"type": "analysis_progress", "entry": {**entry, "state": "waiting"}})
            raise
        except Exception:
            logger.exception("analysis_id=%s node=%s step_index=%s failed", analysis_id, name, index)
            writer({"type": "analysis_progress", "entry": {**entry, "state": "error"}})
            raise
        if name == "match_scenario":
            candidates = update.get("candidates", [])
            label = (f"待确认场景：{candidates[0]['name']}" if len(candidates) == 1 else
                     "匹配到多个场景，等待选择" if candidates else "未匹配到分析场景")
        elif name == "load_template":
            label = f"分析方案：{update['template']['name']}"
        entry = {**entry, "label": label, "state": "waiting" if name == "present_clarification" else "done"}
        writer({"type": "analysis_progress", "entry": entry})
        logger.info("analysis_id=%s node=%s completed", analysis_id, name)
        return {**update, "execution": {entry_id: entry}}
    return run


def track_analysis_step(name, node):
    """仅发送进度事件；UI 字段不进入子图的状态或返回值。"""
    def run(state, config: RunnableConfig, runtime: Runtime[AgentContext]):
        chat = config.get("metadata", {}).get("analysis_chat")
        if not chat:
            return node(state, runtime) if name == "fetch_step_data" else node(state, config)
        update = track_execution(name, lambda view, cfg: (
            node(state, runtime) if name == "fetch_step_data" else node(state, cfg)
        ))({**state, **chat}, config)
        update.pop("execution")
        return update
    return run


def chat_analysis_execution(subgraph, context):
    """父图边界适配：运行元数据传入 config，完成后投影聊天消息。"""
    def run(state: QuestionAnswerState, config: RunnableConfig):
        analysis_id = state["analysis_id"]
        turn = next((m.id for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), analysis_id)
        result = subgraph.invoke({"template": state["template"]},
            merge_configs(config, {"recursion_limit": max(config.get("recursion_limit", 25), 3 * len(state["template"]["steps"]) + 5), "metadata": {"analysis_chat": {
                "analysis_id": analysis_id, "turn_id": turn,
            }}}), context=context)
        messages, execution = [], {}
        for step, outcome in zip(state["template"]["steps"], result["analysis_result"]["step_results"]):
            messages.append(chat_message(state, f"step:{step['step_id']}",
                f"### 步骤 {step['step_id']}：{step['text']}\n\n{outcome['conclusion']}"))
            for name, label in (("fetch_step_data", "查询数据"), ("analyze_step", "生成步骤分析")):
                if name == "fetch_step_data" and not step["metrics"]:
                    continue
                entry_id = f"{analysis_id}:{name}:{step['step_id'] - 1}:{turn}"
                entry = {"id": entry_id, "analysis_id": analysis_id, "state": "done",
                         "label": f"{label} · 步骤 {step['step_id']}：{step['text']}"}
                if name == "analyze_step":
                    entry["message_id"] = f"{analysis_id}:step:{step['step_id']}"
                else:
                    entry["label"] += " · " + "、".join(step["metrics"])
                execution[entry_id] = entry
        return {**result, "messages": messages, "execution": execution,
                "status": "正在生成场景总结"}
    return run
