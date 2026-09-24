"""聊天消息、节点进度和模型流式输出的共享工具。"""

from time import monotonic
import logging

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphInterrupt
from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer
from langgraph.constants import TAG_NOSTREAM
from langchain_core.runnables.config import merge_configs

from life_insurance_business_analysis_assistant.agent.state import ChatState
from life_insurance_business_analysis_assistant.data_coverage import pending_queries

logger = logging.getLogger(__name__)


def chat_message(state: ChatState, suffix: str, text: str, **metadata):
    # reducer 将字典转换为 AIMessage；固定 ID 让 values 覆盖 custom 流的临时消息。
    return {"type": "ai", "content": text, "id": f"{state['analysis_id']}:{suffix}",
            "additional_kwargs": {"analysis": True, "analysis_id": state["analysis_id"], **metadata}}


def track_execution(name, node):
    """聊天边界统一记录节点进度；成功记录写入检查点，失败仍保留原重试语义。"""
    def run(state: ChatState, config: RunnableConfig):
        analysis_id = state["analysis_id"]
        index = state.get("step_index", 0)
        template = state.get("template")
        step = template["steps"][index] if template and index < len(template["steps"]) else None
        labels = {
            "match_scenario": "识别分析场景", "load_template": "加载分析方案",
            "resolve_slots": "解析分析参数", "present_clarification": "请求补充信息",
            "clarify": "等待补充信息", "no_match": "未匹配到分析场景",
            "fetch_step_data": "查询数据", "analyze_step": "生成步骤分析",
            "plan_step": "规划步骤执行",
            "summarize_scenario": "生成场景总结", "recommend_charts": "生成图表推荐",
            "present_charts": "分析报告已完成",
        }
        label = labels[name]
        suffix = None
        if name in ("plan_step", "fetch_step_data", "analyze_step") and step:
            label += f" · 步骤 {step['step_id']}：{step['text']}"
            if name == "analyze_step":
                suffix = f"step:{step['step_id']}"
        elif name == "summarize_scenario":
            suffix = "summary"
        elif name == "recommend_charts":
            suffix = "charts"
        turn = next((m.id for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)), analysis_id)
        entry_id = f"{analysis_id}:{name}:{index}:{turn}"
        if name == "fetch_step_data":
            queries = pending_queries(state)
            if queries:
                entry_id += f":{queries[0]['request_key']}"
                label += " · " + "、".join(queries[0]["requirement"]["metrics"])
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
        elif name == "plan_step":
            plan = update["step_plan"]
            if update.get("clarification"):
                label = "步骤需求待澄清"
            elif plan["queries"]:
                label = "复用并补充查询" if plan["data_uses"] else "查询新数据"
            else:
                label = "复用已有数据" if plan["data_uses"] else "基于已有结论直接分析"
            label += f" · 步骤 {plan['step_id']}"
        entry = {**entry, "label": label, "state": "waiting" if name == "present_clarification" else "done"}
        writer({"type": "analysis_progress", "entry": entry})
        logger.info("analysis_id=%s node=%s completed", analysis_id, name)
        return {**update, "execution": {entry_id: entry}}
    return run


class AnalysisStream(BaseCallbackHandler):
    """合并短时间内的增量；思考和正文分开传输，不暴露结构化 JSON。"""

    run_inline = True

    def __init__(self, state, suffix, heading, *, protocol=True):
        self.writer = get_stream_writer() if state.get("analysis_id") else None
        self.id = f"{state.get('analysis_id')}:{suffix}"
        self.analysis_id = state.get("analysis_id")
        self.heading = heading
        self.protocol = protocol
        self.reasoning = []
        self.pending = {"text": "", "reasoning": ""}
        self.last_flush = monotonic()
        self.status = f"正在思考：{heading}"
        if self.writer:
            self.writer({"type": "analysis_delta", "id": self.id, "start": True,
                         "analysis_id": self.analysis_id, "text": f"### {heading}\n\n", "status": self.status})

    def push(self, field, text):
        if not text:
            return
        if field == "reasoning":
            self.reasoning.append(text)
        else:
            self.status = f"正在生成：{self.heading}"
        self.pending[field] += text
        if monotonic() - self.last_flush >= 0.032:
            self.flush()

    def flush(self):
        if self.writer and any(self.pending.values()):
            self.writer({"type": "analysis_delta", "id": self.id,
                         "analysis_id": self.analysis_id, **self.pending, "status": self.status})
        self.pending = {"text": "", "reasoning": ""}
        self.last_flush = monotonic()

    def on_stream_event(self, event, **kwargs):
        delta = event.get("delta", {})
        if self.protocol and delta.get("type") == "reasoning-delta":
            self.push("reasoning", delta.get("reasoning", ""))

    def on_llm_new_token(self, token, *, chunk=None, **kwargs):
        if not self.protocol and chunk is not None:
            self.push("reasoning", chunk.message.additional_kwargs.get("reasoning_content", ""))
            if token and self.status != f"正在生成：{self.heading}":
                self.flush()
                self.status = f"正在生成：{self.heading}"
                if self.writer:
                    self.writer({"type": "analysis_delta", "id": self.id,
                                 "text": "", "status": self.status})


def stream_text(llm, prompt, config, state, suffix, heading):
    """聊天流使用固定消息 ID；完整文本通过节点返回值提交检查点。"""
    chatting = bool(state.get("analysis_id"))
    progress = AnalysisStream(state, suffix, heading) if chatting else None
    if chatting:
        config = merge_configs(config, {"tags": [TAG_NOSTREAM], "callbacks": [progress]})
    stream = llm.stream_events(prompt, config=config, version="v3")
    parts = []
    try:
        for text in stream.text:
            parts.append(text)
            if progress:
                progress.push("text", text)
        message = stream.output
        if progress:
            message.additional_kwargs["analysis_reasoning"] = "".join(progress.reasoning)
        return "".join(parts).strip(), message
    finally:
        if progress:
            progress.flush()
