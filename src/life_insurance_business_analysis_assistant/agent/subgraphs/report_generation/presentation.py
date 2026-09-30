from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.state import ReportState
from time import monotonic
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import merge_configs
from langgraph.config import get_stream_writer
from langgraph.constants import TAG_NOSTREAM
from life_insurance_business_analysis_assistant.agent.shared.messages import chat_message
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.rendering import build_report


def publish_report(state, *, complete=False, charts_ready=False):
    report = build_report(state, complete=complete, charts_ready=charts_ready)
    # 展示消息只带章节，不重复传送全部原始数据；原始数据保存在业务结果中。
    view = {key: value for key, value in report.items() if key != "datasets"}
    message = chat_message(state, "report", report["markdown"], report=view)
    get_stream_writer()({"type": "report_snapshot", "report": view})
    return {"report_result": report, "messages": [message],
            "status": "已完成" if complete else "正在生成报告"}


def stream_report_text(llm, prompt, config, state, suffix, heading):
    """只向章节发送累计正文快照；重放和重试不会追加重复文字。"""
    writer = get_stream_writer()
    step = state["current_step"]
    event = {"type": "report_step", "report_id": state["report_id"],
             "section_id": step["section_id"], "step_id": step["step_id"]}
    writer({**event, "text": "", "status": "generating"})
    parts, last_flush = [], monotonic()
    try:
        stream = llm.stream_events(prompt, config=merge_configs(config, {"tags": [TAG_NOSTREAM]}), version="v3")
        for text in stream.text:
            parts.append(text)
            if monotonic() - last_flush >= 0.032:
                writer({**event, "text": "".join(parts), "status": "generating"})
                last_flush = monotonic()
        writer({**event, "text": "".join(parts), "status": "generating"})
        return "".join(parts).strip(), stream.output
    except Exception:
        writer({**event, "text": "".join(parts), "status": "error"})
        raise


def track_report_node(name, label, node):
    def run(state: ReportState, config: RunnableConfig):
        step = state.get("current_step") if name in ("fetch_report_step_data", "analyze_report_step", "commit_report_step") else None
        entry_id = f"{state['report_id']}:{name}:{step['step_id'] if step else 0}"
        description = label
        if step:
            description += " · " + " / ".join(step["section_path"]) + " · " + step["text"]
        entry = {"id": entry_id, "analysis_id": state["analysis_id"], "label": description, "state": "running"}
        writer = get_stream_writer()
        writer({"type": "analysis_progress", "entry": entry})
        try:
            update = node(state, config)
        except Exception:
            writer({"type": "analysis_progress", "entry": {**entry, "state": "error"}})
            raise
        entry = {**entry, "state": "done"}
        writer({"type": "analysis_progress", "entry": entry})
        return {**update, "execution": {entry_id: entry}}
    return run
