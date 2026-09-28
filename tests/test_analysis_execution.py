"""独立子图契约、逐节点提交、校验和父图失败恢复；完全离线。"""
import asyncio
from copy import deepcopy
from unittest import TestCase

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime
from langgraph.types import Command

from life_insurance_business_analysis_assistant.agent.graph import build_analysis_graph, build_chat_graph
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.state import AgentState, create_initial_state
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.graph import build_analysis_execution_graph
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.nodes.finalize_subgraph import finalize_subgraph
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.nodes.initialize_subgraph import initialize_subgraph
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.nodes.load_step import load_step
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.state import (
    AnalysisExecutionInput, AnalysisExecutionOutput, AnalysisExecutionState, StepResult,
)
from workflow_support import context, models, patched_models, payload


def test_analysis_execution():
    assert set(AnalysisExecutionInput.__annotations__) == {"template"}
    assert set(AnalysisExecutionOutput.__annotations__) == {"analysis_result"}
    assert set(AnalysisExecutionState.__annotations__) == {
        "template", "step_index", "current_step", "datasets", "step_results",
    }
    assert set(StepResult.__annotations__) == {"step_id", "dataset_ids", "conclusion"}
    assert not {"step_index", "current_step", "datasets", "step_results"} & AgentState.__annotations__.keys()
    assert create_initial_state("标保")["analysis_result"] is None
    ctx, mock = context(), models()
    template = load_template({"scenario_id": "standard_premium_review"}, Runtime(context=ctx))["template"]
    template["steps"] = template["steps"][:3]
    template["steps"][1]["metrics"] = []
    graph = build_analysis_execution_graph().builder.compile(checkpointer=InMemorySaver())
    assert set(graph.get_input_jsonschema()["properties"]) == {"template"}
    assert set(graph.get_output_jsonschema()["properties"]) == {"analysis_result"}
    # Studio /assistants/{id}/subgraphs 会递归读取 context Schema。
    for parent in (build_analysis_graph(), build_chat_graph(studio_context=ctx)):
        children = list(parent.get_subgraphs(recurse=True))
        assert children
        for _, child in children:
            schema = child.get_context_jsonschema()
            assert set(schema["properties"]) == {"scenario_catalog", "template_path"}
            assert set(schema["$defs"]["ScenarioEntry"]["properties"]) == {
                "scenario_id", "name", "keywords",
            }
    config = {"configurable": {"thread_id": "subgraph"}, "recursion_limit": 100}
    with patched_models(mock):
        updates = list(graph.stream({"template": template}, config, context=ctx, stream_mode="updates"))
    expected = ["initialize_subgraph", "load_step", "fetch_step_data", "analyze_step",
                "load_step", "analyze_step", "load_step", "fetch_step_data", "analyze_step", "finalize_subgraph"]
    assert [next(iter(update)) for update in updates] == expected
    assert [u["analyze_step"]["step_index"] for u in updates if "analyze_step" in u] == [1, 2, 3]
    assert all(set(u["fetch_step_data"]) == {"datasets"} for u in updates if "fetch_step_data" in u)
    output = updates[-1]["finalize_subgraph"]
    assert set(output) == {"analysis_result"}
    result = output["analysis_result"]
    assert set(result) == {"datasets", "step_results"}
    assert [r["step_id"] for r in result["step_results"]] == [1, 2, 3]
    assert result["step_results"][1]["dataset_ids"] == []
    assert set(result["datasets"]) == {"step:1:table:1", "step:3:table:1"}
    assert ctx.query_data.call_count == 2
    sent = payload(mock["analyze_step"].stream_events.call_args_list[1].args[0])
    assert sent["datasets"] == [] and [c["step_id"] for c in sent["conclusions"]] == [1]
    saved = graph.get_state(config).values
    for change in ("index", "missing", "order", "reference", "owner", "empty"):
        invalid = deepcopy(saved)
        if change == "index": invalid["step_index"] = 2
        elif change == "missing": invalid["step_results"].pop()
        elif change == "order": invalid["step_results"].reverse()
        elif change == "reference": invalid["datasets"].clear()
        elif change == "owner": invalid["datasets"]["step:1:table:1"]["step_id"] = 3
        else: invalid["step_results"][0]["conclusion"] = " "
        with TestCase().assertRaises(ValueError):
            finalize_subgraph(invalid)
    for index in (-1, True, 3):
        with TestCase().assertRaises(ValueError):
            load_step({**saved, "step_index": index})
    invalid = deepcopy(saved)
    invalid["step_index"] = 0
    invalid["template"]["steps"][0]["metrics"] = [""]
    with TestCase().assertRaises(ValueError):
        load_step(invalid)
    with TestCase().assertRaises(ValueError):
        initialize_subgraph({"template": {**template, "steps": []}})

    # 父图只停在子图边界；子图保存查询成功后的状态，重建图也能恢复。
    ctx, mock = context(), models()
    graph = build_analysis_graph()
    saver = graph.checkpointer
    config = {"configurable": {"thread_id": "parent-retry"}, "recursion_limit": 100}
    original = mock["analyze_step"].stream_events.side_effect
    mock["analyze_step"].stream_events.side_effect = RuntimeError("分析失败")
    with patched_models(mock):
        graph.invoke(create_initial_state("标保"), config, context=ctx)
        with TestCase().assertRaisesRegex(RuntimeError, "分析失败"):
            graph.invoke(Command(resume="standard_premium_review"), config, context=ctx)
        parent = graph.get_state(config, subgraphs=True)
        child = parent.tasks[0].state
        assert parent.next == ("analysis_execution",) and parent.values["analysis_result"] is None
        assert child.next == ("analyze_step",) and child.values["step_index"] == 0
        assert len(child.values["datasets"]) == 1 and child.values["step_results"] == []
        mock["summarize_scenario"].stream_events.assert_not_called()
        mock["recommend_charts"].with_structured_output.return_value.invoke.assert_not_called()
        mock["analyze_step"].stream_events.side_effect = original
        graph = build_analysis_graph().builder.compile(checkpointer=saver)
        result = graph.invoke(None, config, context=ctx)
    assert ctx.query_data.call_count == 5 and result["summary"] and result["chart_recommendations"]
    summary = payload(mock["summarize_scenario"].stream_events.call_args.args[0])
    assert summary["step_results"] == result["analysis_result"]["step_results"]
    assert summary["datasets"] == {key: record["payload"] for key, record in result["analysis_result"]["datasets"].items()}
    print("subgraph contracts, routing, validation, checkpoints and parent recovery: PASS")


def test_async_chat():
    ctx, mock = context(), models()
    graph = build_chat_graph(studio_context=ctx).builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "async-subgraph"}, "recursion_limit": 100}

    async def run():
        for turn in ("first", "second"):
            await graph.ainvoke({"messages": [{"type": "human", "content": "价值", "id": turn}]}, config)
            events = [e async for e in graph.astream(Command(resume="value_review"), config,
                       stream_mode=["custom", "values"], subgraphs=True)]
            result = (await graph.aget_state(config)).values
            assert result["analysis_id"] == turn and len(result["analysis_result"]["step_results"]) == 3
            assert len(result["analysis_result"]["datasets"]) == 3
            assert any(ns and kind == "custom" and data.get("id") == f"{turn}:step:1"
                       for ns, kind, data in events)
            assert len([m for m in result["messages"] if m.id.startswith(f"{turn}:step:")]) == 3
            assert all(e["state"] == "done" for e in result["execution"].values()
                       if e["analysis_id"] == turn and ":step:" in e.get("message_id", ""))
        assert ctx.query_data.call_count == 6

    with patched_models(mock):
        asyncio.run(run())
    print("async nested custom stream and repeated chat analysis isolation: PASS")


if __name__ == "__main__":
    test_analysis_execution()
    test_async_chat()
