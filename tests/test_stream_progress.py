"""运行 python -B tests/test_stream_progress.py；模拟 DeepSeek 的真实 SSE 数据形状。"""

from itertools import count
import asyncio
from threading import Event
from unittest.mock import MagicMock, patch

from langchain_deepseek import ChatDeepSeek
from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver

from life_insurance_business_analysis_assistant.agent.chat import AnalysisStream, chat_message, stream_text
from life_insurance_business_analysis_assistant.agent.state import ChatState
from life_insurance_business_analysis_assistant.agent.nodes.recommend_charts import ChartDecision


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
                assert received.wait(5), "异步图必须在模型结束前转发思考事件"
            else:
                assert any(e.get("reasoning") for e in events), "思考必须在正文生成前送达"
            for char in text:
                yield {"choices": [{"delta": {"content": char}, "finish_reason": None}]}
            yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        result = MagicMock()
        result.__enter__.return_value = chunks()
        # 普通 SSE 响应没有 SDK structured-output 的 get_final_completion。
        del result.get_final_completion
        return result

    with patch("life_insurance_business_analysis_assistant.agent.chat.get_stream_writer", return_value=events.append), \
         patch("life_insurance_business_analysis_assistant.agent.chat.monotonic", side_effect=lambda: next(clock) * 0.04):
        client.create.return_value = response("整体总结")
        text, message = stream_text(model, "总结", {}, {"analysis_id": "q1"}, "summary", "场景总结")
        assert text == "整体总结"
        assert message.additional_kwargs["analysis_reasoning"] == "先核对指标再比较趋势"
        assert "".join(e.get("reasoning", "") for e in events) == "先核对指标再比较趋势"
        assert "".join(e["text"] for e in events) == "### 场景总结\n\n整体总结"
        assert len([e for e in events if e.get("text") and not e.get("start")]) > 1

        # 图表保持结构化校验，但请求采用真实流式传输，思考可提前显示。
        events.clear()
        root_client.beta.chat.completions.stream.return_value = response('{"recommended":false,"chart_type":null,"step_id":1,"dimensions":[],"metrics":[],"reason":"数据不足","description":"阅读结论"}')
        progress = AnalysisStream({"analysis_id": "q1"}, "charts", "图表推荐", protocol=False)
        decision = model.with_structured_output(ChartDecision, method="json_mode").invoke(
            "推荐图表", config={"callbacks": [progress]}, stream=True,
        )
        progress.flush()
        root_client.beta.chat.completions.stream.assert_called_once()
        assert decision.recommended is False
        assert "".join(progress.reasoning) == "先核对指标再比较趋势"
        assert "".join(e["text"] for e in events) == "### 图表推荐\n\n", "不可显示半成品 JSON"

        # 连续短片段合并发送，末尾不足一个周期的内容仍需刷新。
        events.clear()
        with patch("life_insurance_business_analysis_assistant.agent.chat.monotonic", return_value=0):
            progress = AnalysisStream({"analysis_id": "q1"}, "summary", "场景总结")
            for _ in range(100):
                progress.push("text", "字")
            assert len(events) == 1
            progress.flush()
            assert len(events) == 2 and events[-1]["text"] == "字" * 100

    # Agent Server 使用异步图：消费端收到思考前模型不会继续，排除节点结束后集中输出。
    received = Event()
    client.create.return_value = response("整体总结", received)

    def summarize(state, config):
        text, message = stream_text(model, "总结", config, state, "summary", "场景总结")
        return {"messages": [chat_message(state, "summary", text,
                                         reasoning=message.additional_kwargs["analysis_reasoning"])]}

    builder = StateGraph(ChatState)
    builder.add_node("summarize", summarize)
    builder.add_edge(START, "summarize")
    builder.add_edge("summarize", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "stream-progress"}}

    async def consume():
        async for kind, data in graph.astream({"analysis_id": "q1", "messages": []}, config,
                                             stream_mode=["custom", "values"]):
            if kind == "custom" and data.get("reasoning"):
                received.set()
        saved = (await graph.aget_state(config)).values["messages"][-1]
        assert saved.content == "整体总结"
        assert saved.additional_kwargs["reasoning"] == "先核对指标再比较趋势"

    with patch("life_insurance_business_analysis_assistant.agent.chat.monotonic", side_effect=lambda: next(clock) * 0.04):
        asyncio.run(consume())
    print("reasoning before text, summary deltas, structured chart streaming and batching: PASS")


if __name__ == "__main__":
    test_stream_progress()
