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
    """只合并显式提交的正文增量；模型回调不转发内部推理或 JSON。"""

    run_inline = True

    def __init__(self, state, suffix, heading):
        self.writer = get_stream_writer() if state.get("analysis_id") else None
        self.id = f"{state.get('analysis_id')}:{suffix}"
        self.analysis_id = state.get("analysis_id")
        self.heading = heading
        self.pending = ""
        self.last_flush = monotonic()
        self.status = f"正在生成：{heading}"
        if self.writer:
            self.writer({"type": "analysis_delta", "id": self.id, "start": True,
                         "analysis_id": self.analysis_id, "text": f"### {heading}\n\n", "status": self.status})

    def push(self, text):
        if not text:
            return
        self.pending += text
        if monotonic() - self.last_flush >= 0.032:
            self.flush()

    def flush(self):
        if self.writer and self.pending:
            self.writer({"type": "analysis_delta", "id": self.id,
                         "analysis_id": self.analysis_id, "text": self.pending, "status": self.status})
        self.pending = ""
        self.last_flush = monotonic()

def stream_text(llm, prompt, config, state, suffix, heading):
    """聊天流使用固定消息 ID；完整文本通过节点返回值提交检查点。"""
    state = config.get("metadata", {}).get("analysis_chat") or state
    chatting = bool(state.get("analysis_id"))
    progress = AnalysisStream(state, suffix, heading) if chatting else None
    # 独立图也可能订阅 messages，所有模型原始流均需关闭。
    config = merge_configs(config, {"tags": [TAG_NOSTREAM]})
    stream = llm.stream_events(prompt, config=config, version="v3")
    parts = []
    try:
        for text in stream.text:
            parts.append(text)
            if progress:
                progress.push(text)
        message = stream.output
        return "".join(parts).strip(), message
    finally:
        if progress:
            progress.flush()
