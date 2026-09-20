"""运行 python -B tests/test_chat.py：聊天流、检查点重试、输入边界及多轮隔离。"""

import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.checkpoint.memory import InMemorySaver

from life_insurance_business_analysis_assistant.agent.context import AgentContext, load_scenario_catalog
from life_insurance_business_analysis_assistant.agent.graph import build_graph
from life_insurance_business_analysis_assistant.data_query import make_fake_query


def test_chat():
    path = Path(__file__).resolve().parents[1] / "config/templates/Scenario/场景分析模板.yaml"
    slots = {"年份": 2026, "月份": 8, "渠道": "个险", "机构范围": "全系统"}
    query = Mock(side_effect=make_fake_query(slots))
    context = AgentContext(load_scenario_catalog(path), path, query)
    graph = build_graph(studio_context=context).builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "chat-retry"}}
    extractor, analyzer, charts = Mock(), Mock(), Mock()
    extractor.with_structured_output.return_value.invoke.return_value = {"values": slots, "ambiguous": {}}
    charts.with_structured_output.return_value.invoke.return_value = {
        "recommended": False, "chart_type": None, "step_id": 1, "dimensions": [], "metrics": [],
        "reason": "总体数据无需图表", "description": "阅读分析结论",
    }
    failed = False

    def analyze(messages, **kwargs):
        nonlocal failed
        step = json.loads(messages[1][1])["step"]["step_id"]
        if step == 2 and not failed:
            failed = True

            class BrokenStream:
                @property
                def text(self):
                    yield "尚未完成"
                    raise RuntimeError("模拟连接中断")

            return BrokenStream()
        return FakeListChatModel(responses=[f"步骤{step}结论"]).stream_events(messages, **kwargs)

    analyzer.stream_events.side_effect = analyze
    with ExitStack() as stack:
        for node, model in [("resolve_slots", extractor), ("analyze_step", analyzer),
                            ("summarize_scenario", FakeListChatModel(responses=["整体总结"])),
                            ("recommend_charts", charts)]:
            stack.enter_context(patch(f"life_insurance_business_analysis_assistant.agent.nodes.{node}.get_llm", return_value=model))
        events = []
        try:
            for event in graph.stream({"messages": [{"type": "human", "id": "q1", "content": "2026年8月标保"}]},
                                      config, stream_mode=["custom", "values", "messages"]):
                events.append(event)
        except RuntimeError as error:
            assert str(error) == "模拟连接中断"
        else:
            raise AssertionError("应暴露模型中断")
        paused = graph.get_state(config)
        assert paused.next == ("analyze_step",)
        assert paused.values["step_index"] == 1
        assert len(paused.values["step_results"]) == 1
        assert "q1:step:1" in [message.id for message in paused.values["messages"]]
        assert "q1:step:2" not in [message.id for message in paused.values["messages"]]
        assert any(kind == "custom" and data.get("text") == "尚未完成" for kind, data in events)
        # 以空输入恢复失败检查点，不重新执行已完成步骤或重复取数。
        resumed = list(graph.stream(None, config, stream_mode=["custom", "values", "messages"]))
        result = graph.get_state(config).values
        assert result["status"] == "已完成"
        assert query.call_count == len(result["template"]["steps"])
        assert len(result["messages"]) == len(result["template"]["steps"]) + 3
        assert len({message.id for message in result["messages"]}) == len(result["messages"])
        assert any(kind == "custom" and data.get("id") == "q1:step:2" and data.get("start") for kind, data in resumed)
        # 聊天流与检查点文本逐字一致，失败尝试的半成品未写入业务状态。
        streamed = {}
        for kind, data in events + resumed:
            if kind == "messages":
                message, _ = data
                assert message.type == "human", "AI 文本仅经 custom/values 发布，不应再经原生 messages 流重复发送"
            if kind == "custom" and data.get("type") == "analysis_delta":
                streamed[data["id"]] = ("" if data.get("start") else streamed.get(data["id"], "")) + data["text"]
        for message in result["messages"]:
            if message.id in streamed:
                assert message.content == streamed[message.id]
        before = len(result["messages"])
        # 消息输入无需重复携带 question，不能被上一轮 question 覆盖。
        second = graph.invoke({"messages": [{"type": "human", "id": "q2", "content": [{"type": "text", "text": "人力"}]}]}, config)
        assert second["question"] == "人力" and second["analysis_id"] == "q2"
        assert second["slots"] == {} and second["step_results"] == [] and second["summary"] is None
        assert len(second["messages"]) == before + 2
        third = graph.invoke({"question": "人员情况"}, config)
        assert third["question"] == "人员情况" and third["status"] == "已完成"
        for i, invalid in enumerate([
            {"messages": [{"type": "human", "content": "  "}]},
            {"messages": [{"type": "human", "content": [{"type": "image_url", "image_url": "x"}]}]},
            {"question": 3},
            {"question": "标保", "messages": [{"type": "human", "content": "价值"}]},
        ]):
            try:
                graph.invoke(invalid, {"configurable": {"thread_id": f"invalid-{i}"}})
            except ValueError:
                pass
            else:
                raise AssertionError(f"未拒绝无效输入：{invalid}")
    print("chat streaming, checkpoint retry, multi-turn reset and validation: PASS")


if __name__ == "__main__":
    test_chat()
