"""python -B tests/test_workflow_integration.py；完整图及真实检查点，LLM/数据均为显式模拟。"""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from life_insurance_business_analysis_assistant.agent.graph import build_analysis_graph, build_chat_graph
from life_insurance_business_analysis_assistant.agent.state import create_initial_state
from workflow_support import context, models, patched_models, payload, SLOTS


def test_workflow_integration(studio=False, chat=False):
    cases = [
        ("single", "2026年8月个险全系统标保", ["standard_premium_review"], 3),
        ("slots", "2026年标保", ["standard_premium_review", "8月"], 3),
        ("month_only", "标保", ["standard_premium_review", "2026年8月"], 3),
        ("value_month_only", "价值", ["value_review", "2026年8月"], 2),
        ("choice", "2026年8月个险全系统标保和价值", ["value_review"], 2),
        ("both", "标保和价值", ["standard_premium_review", "2026年8月个险全系统"], 3),
        ("zero", "人力情况", [], 0),
    ]
    for name, question, replies, query_count in cases:
        ctx, mock = context(), models()
        graph = build_chat_graph(studio_context=ctx) if studio else build_analysis_graph()
        if studio:
            graph.get_input_jsonschema()
            graph.get_output_jsonschema()
            graph = graph.builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": name}, "recursion_limit": 100}
        initial = {"messages": [{"type": "human", "id": name, "content": question}]} if chat else {"question": question}
        with patched_models(mock):
            result = graph.invoke(initial if studio else create_initial_state(question), config, context=ctx)
            for index, reply in enumerate(replies):
                interrupt = result["__interrupt__"][0]
                assert interrupt.value["kind"] == ("scenario_selection" if index == 0 else "slot_completion")
                assert ctx.query_data.call_count == 0
                if index == 0:
                    assert result["scenario_id"] is None  # 单候选也必须明确确认。
                result = graph.invoke(Command(resume={interrupt.id: reply}), config, context=ctx)
            assert "__interrupt__" not in result
            assert not graph.get_state(config).next
            assert ctx.query_data.call_count == query_count
            if not query_count:
                assert result["summary"] is None
                continue
            assert result["slots"] == SLOTS
            steps = result["template"]["steps"]
            assert len(result["step_results"]) == result["step_index"] == len(steps)
            assert result["step_plan"] is None
            assert len(result["datasets"]) == query_count
            assert len({call.args[0]["request_key"] for call in ctx.query_data.call_args_list}) == query_count
            assert all("data" not in entry for entry in result["step_results"])
            assert result["step_results"][1]["data_uses"][0]["dataset_id"] == result["step_results"][2]["data_uses"][0]["dataset_id"]
            for call in mock["analyze_step"].stream_events.call_args_list:
                assert payload(call.args[0])["datasets"]
            assert result["summary"] == "模拟场景总结"
            chart = result["chart_recommendations"][0]
            assert chart["recommended"] and chart["step_id"] == 2 and chart["data"]
            assert all(isinstance(row[chart["metrics"][0]], float) for row in chart["data"])
            assert "模拟" in chart["description"]
            if studio:
                assert result["status"] == "已完成"
                assert result["messages"][-1].additional_kwargs["charts"] == result["chart_recommendations"]
                ids = [m.id for m in result["messages"]]
                assert len(ids) == len(set(ids))
        print(f"workflow {name}: PASS")


if __name__ == "__main__":
    test_workflow_integration()
    test_workflow_integration(studio=True)
    test_workflow_integration(studio=True, chat=True)
