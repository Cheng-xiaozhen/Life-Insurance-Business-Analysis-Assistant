"""固定消息标识和模型文本流的基础输出工具。"""

from time import monotonic
from langchain_core.callbacks import BaseCallbackHandler
from langgraph.config import get_stream_writer
from langgraph.constants import TAG_NOSTREAM
from langchain_core.runnables.config import merge_configs
from life_insurance_business_analysis_assistant.agent.shared.contracts import MessageState


def chat_message(state: MessageState, suffix: str, text: str, **metadata):
    # reducer 将字典转换为 AIMessage；固定 ID 让 values 覆盖 custom 流的临时消息。
    return {
        "type": "ai",
        "content": text,
        "id": f"{state['analysis_id']}:{suffix}",
        "additional_kwargs": {
            "analysis": True,
            "analysis_id": state["analysis_id"],
              **metadata}
                              }


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
    state = config.get("metadata", {}).get("analysis_chat") or state
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
