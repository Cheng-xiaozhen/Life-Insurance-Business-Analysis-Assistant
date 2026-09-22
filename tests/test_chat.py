"""python -B tests/test_chat.py；流式半成品隔离、失败恢复与多轮消息兼容。"""

from copy import deepcopy
from unittest import TestCase

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from life_insurance_business_analysis_assistant.agent.graph import build_graph
from workflow_support import context, models, patched_models, payload


def test_chat():
    ctx, mock = context(), models()
    graph = build_graph(studio_context=ctx).builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "chat-retry"}, "recursion_limit": 100}
    original = mock["analyze_step"].stream_events.side_effect
    failed = False
    def analyze(messages, **kwargs):
        nonlocal failed
        if payload(messages)["step"]["step_id"] == 2 and not failed:
            failed = True
            class BrokenStream:
                @property
                def text(self):
                    yield "尚未完成"
                    raise RuntimeError("模拟连接中断")
            return BrokenStream()
        return original(messages, **kwargs)
    mock["analyze_step"].stream_events.side_effect = analyze
    with patched_models(mock):
        paused = graph.invoke({"messages": [{"type": "human", "id": "q1", "content": "2026年8月个险全系统标保"}]}, config)
        interrupt = paused["__interrupt__"][0]
        assert interrupt.value["kind"] == "scenario_selection"
        events = []
        with TestCase().assertLogs("life_insurance_business_analysis_assistant.agent.chat", level="ERROR"):
            try:
                for event in graph.stream(Command(resume={interrupt.id: "standard_premium_review"}), config, stream_mode=["custom", "values", "messages"]):
                    events.append(event)
            except RuntimeError as error:
                assert str(error) == "模拟连接中断"
            else:
                raise AssertionError("模拟中断应抛出异常")
        saved = graph.get_state(config)
        assert saved.next == ("analyze_step",)
        assert saved.values["step_index"] == 1 and len(saved.values["step_results"]) == 1
        assert len(saved.values["datasets"]) == 2
        assert "q1:step:2" not in [m.id for m in saved.values["messages"]]
        assert any(kind == "custom" and data.get("text") == "尚未完成" for kind, data in events)
        plan_calls = mock["plan_step"].with_structured_output.return_value.invoke.call_count
        resumed = list(graph.stream(None, config, stream_mode=["custom", "values", "messages"]))
        result = graph.get_state(config).values
        assert result["status"] == "已完成" and ctx.query_data.call_count == 3
        assert mock["plan_step"].with_structured_output.return_value.invoke.call_count == plan_calls + 3
        assert len({m.id for m in result["messages"]}) == len(result["messages"])
        streamed = {}
        for kind, data in events + resumed:
            if kind == "messages":
                message, _ = data
                assert message.type == "human", "AI 仅通过 custom/values 输出，不能重复发送"
            if kind == "custom" and data.get("type") == "analysis_delta":
                streamed[data["id"]] = ("" if data.get("start") else streamed.get(data["id"], "")) + data["text"]
        for message in result["messages"]:
            if message.id in streamed:
                assert message.content == streamed[message.id]
        charts = deepcopy(result["messages"][-1].additional_kwargs["charts"])
        second = graph.invoke({"question": None, "messages": [{"type": "human", "id": "q2", "content": "人力"}]}, config)
        assert second["analysis_id"] == "q2" and second["datasets"] == {} and second["step_plan"] is None
        assert second["slots"] == {} and second["step_results"] == [] and second["summary"] is None
        assert next(m for m in second["messages"] if m.id == "q1:charts").additional_kwargs["charts"] == charts
        assert any(entry["analysis_id"] == "q1" for entry in second["execution"].values())
        for index, invalid in enumerate([
            {"messages": [{"type": "human", "content": " "}]},
            {"messages": [{"type": "human", "content": [{"type": "image_url", "image_url": "x"}]}]},
            {"question": 3}, {"question": "标保", "messages": [{"type": "human", "content": "价值"}]},
        ]):
            try:
                graph.invoke(invalid, {"configurable": {"thread_id": f"invalid-{index}"}})
            except ValueError:
                pass
            else:
                raise AssertionError("输入边界未拒绝非法数据")
    print("chat streaming, checkpoint retry, chart history and multi-turn isolation: PASS")


if __name__ == "__main__":
    test_chat()
