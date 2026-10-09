"""运行 python -B tests/test_stream_progress.py；模拟 DeepSeek 的真实 SSE 数据形状。"""

from itertools import count
import asyncio
from threading import Event
from unittest.mock import MagicMock, patch

from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import AIMessage
from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver

from life_insurance_business_analysis_assistant.agent.shared.messages import AnalysisStream, chat_message, stream_text
from life_insurance_business_analysis_assistant.agent.state import ChatState
from life_insurance_business_analysis_assistant.agent.shared.charts import ChartDecision
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.presentation import stream_report_text
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.nodes.present_charts import present_charts


def test_stream_progress():
    events = []
    client = MagicMock()
    root_client = MagicMock()
    model = ChatDeepSeek(model="deepseek-chat", api_key="test", client=client, root_client=root_client)
    clock = count()

    def response(text, received=None):
        def chunks():
            yield {"choices": [{"delta": {"role": "assistant", "reasoning_content": "先核对指标"}, "finish_reason": None}]}
            yield {"choices": [{"delta": {"reasoning_content": "再比较趋势"}, "finish_reason": None}]}
            if received is not None:
                assert received.wait(5), "异步图必须在模型结束前转发操作状态"
            else:
                assert all("reasoning" not in e for e in events), "推理不得发送到前端"
            for char in text:
                yield {"choices": [{"delta": {"content": char}, "finish_reason": None}]}
            yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        result = MagicMock()
        result.__enter__.return_value = chunks()
        # 普通 SSE 响应没有 SDK structured-output 的 get_final_completion。
        del result.get_final_completion
        return result

    with patch("life_insurance_business_analysis_assistant.agent.shared.messages.get_stream_writer", return_value=events.append), \
         patch("life_insurance_business_analysis_assistant.agent.shared.messages.monotonic", side_effect=lambda: next(clock) * 0.04):
        client.create.return_value = response("整体总结")
        text, message = stream_text(model, "总结", {}, {"analysis_id": "q1"}, "summary", "场景总结")
        assert text == "整体总结"
        assert "analysis_reasoning" not in message.additional_kwargs
        assert all("reasoning" not in e for e in events)
        assert "".join(e["text"] for e in events) == "### 场景总结\n\n整体总结"
        assert len([e for e in events if e.get("text") and not e.get("start")]) > 1

        # 图表保持结构化校验，流式传输不暴露推理或半成品 JSON。
        events.clear()
        root_client.beta.chat.completions.stream.return_value = response('{"recommended":false,"chart_type":null,"step_id":1,"dimensions":[],"metrics":[],"reason":"数据不足","description":"阅读结论"}')
        progress = AnalysisStream({"analysis_id": "q1"}, "charts", "图表推荐")
        decision = model.with_structured_output(ChartDecision, method="json_mode").invoke(
            "推荐图表", config={"callbacks": [progress]}, stream=True,
        )
        progress.flush()
        root_client.beta.chat.completions.stream.assert_called_once()
        assert decision.recommended is False
        assert not hasattr(progress, "reasoning")
        assert all("reasoning" not in e for e in events)
        assert "".join(e["text"] for e in events) == "### 图表推荐\n\n", "不可显示半成品 JSON"

        # 连续短片段合并发送，末尾不足一个周期的内容仍需刷新。
        events.clear()
        with patch("life_insurance_business_analysis_assistant.agent.shared.messages.monotonic", return_value=0):
            progress = AnalysisStream({"analysis_id": "q1"}, "summary", "场景总结")
            for _ in range(100):
                progress.push("字")
            assert len(events) == 1
            progress.flush()
            assert len(events) == 2 and events[-1]["text"] == "字" * 100

    # Agent Server 使用异步图：消费端收到操作状态前模型不会继续，排除节点结束后集中输出。
    received = Event()
    client.create.return_value = response("整体总结", received)

    def summarize(state, config):
        text, _ = stream_text(model, "总结", config, state, "summary", "场景总结")
        return {"messages": [chat_message(state, "summary", text)]}

    builder = StateGraph(ChatState)
    builder.add_node("summarize", summarize)
    builder.add_edge(START, "summarize")
    builder.add_edge("summarize", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "stream-progress"}}

    async def consume():
        async for kind, data in graph.astream({"analysis_id": "q1", "messages": []}, config,
                                             stream_mode=["custom", "messages", "values"]):
            assert "先核对指标" not in str(data) and "再比较趋势" not in str(data)
            if kind == "custom" and data.get("start"):
                received.set()
        saved = (await graph.aget_state(config)).values["messages"][-1]
        assert saved.content == "整体总结"
        assert "reasoning" not in saved.additional_kwargs

    with patch("life_insurance_business_analysis_assistant.agent.shared.messages.monotonic", side_effect=lambda: next(clock) * 0.04):
        asyncio.run(consume())
    # 无聊天标识的独立图同样关闭原生模型消息流。
    def independent(state, config):
        text, _ = stream_text(model, "总结", config, {}, "summary", "场景总结")
        return {"summary": text}

    independent_builder = StateGraph(ChatState)
    independent_builder.add_node("summary", independent)
    independent_builder.add_edge(START, "summary")
    independent_builder.add_edge("summary", END)
    client.create.return_value = response("独立总结")
    chunks = list(independent_builder.compile().stream({}, stream_mode=["messages", "values"]))
    assert all(kind != "messages" for kind, _ in chunks)
    assert chunks[-1][1]["summary"] == "独立总结"

    # 报告只输出累计正文，原生消息和最终结果也不包含内部推理。
    def report(state, config):
        text, _ = stream_report_text(model, "报告", config, {
            "report_id": "r1", "current_step": {"section_id": "s1", "step_id": 1},
        }, "step:1", "章节")
        return {"messages": [chat_message(state, "report", text)]}

    report_builder = StateGraph(ChatState)
    report_builder.add_node("report", report)
    report_builder.add_edge(START, "report")
    report_builder.add_edge("report", END)
    client.create.return_value = response("报告正文")
    chunks = list(report_builder.compile().stream({"analysis_id": "r1", "messages": []},
                                                  stream_mode=["custom", "messages", "values"]))
    assert "先核对指标" not in str(chunks) and "reasoning" not in str(chunks)
    assert [data for kind, data in chunks if kind == "custom"][-1]["text"] == "报告正文"
    assert chunks[-1][1]["messages"][-1].content == "报告正文"

    # 完成图表不复用历史临时消息中的推理元数据。
    events.clear()
    with patch("life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.nodes.present_charts.get_stream_writer", return_value=events.append):
        update = present_charts({"analysis_id": "q1", "chart_recommendations": [decision.model_dump()],
                                 "messages": [AIMessage(content="", id="q1:charts",
                                                        additional_kwargs={"reasoning": "历史内部推理"})]})
    assert "reasoning" not in str(update) and "reasoning" not in str(events)
    print("public text/progress, hidden reasoning, native message boundary, report and batching: PASS")


if __name__ == "__main__":
    test_stream_progress()
