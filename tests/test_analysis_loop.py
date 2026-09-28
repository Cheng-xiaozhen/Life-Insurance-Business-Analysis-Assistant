"""确定性路由、无数据步骤、多步循环、检查点失败恢复。"""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from langgraph.types import Command
from langgraph.checkpoint.memory import InMemorySaver
from omegaconf import OmegaConf
from life_insurance_business_analysis_assistant.scenario_store import read_scenarios
from life_insurance_business_analysis_assistant.agent.graph import build_analysis_graph, build_chat_graph, route_analysis
from life_insurance_business_analysis_assistant.agent.state import create_initial_state
from workflow_support import TEMPLATE, context, models, patched_models, payload


def test_analysis_loop():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "scenario.yaml"
        for chatting, count in ((False, 0), (False, 1), (False, 3), (False, 15), (True, 0), (True, 3)):
            source = deepcopy(read_scenarios(TEMPLATE)[0])
            first = source["分析思路"][0]
            source["分析思路"] = [{**deepcopy(first), "步骤序号": i + 1} for i in range(count)]
            source["分析思路"].append({"步骤序号": count + 1, "分析步骤": "综合前序结论；无依据时说明限制", "指标": []})
            OmegaConf.save(OmegaConf.create(source), path)
            ctx, mock = context(path), models()
            graph = build_chat_graph(studio_context=ctx).builder.compile(checkpointer=InMemorySaver()) if chatting else build_analysis_graph()
            assert "plan_step" not in graph.builder.nodes and "resolve_slots" not in graph.builder.nodes
            config = {"configurable": {"thread_id": f"loop-{count}"}, "recursion_limit": 200}
            with patched_models(mock):
                graph.invoke(create_initial_state("标保"), config, context=ctx)
                result = graph.invoke(Command(resume="standard_premium_review"), config, context=ctx)
            assert ctx.query_data.call_count == count
            assert result["step_index"] == len(result["step_results"]) == count + 1
            assert result["step_results"][-1]["dataset_ids"] == []
            assert result["step_results"][-1]["conclusion_step_ids"] == list(range(1, count + 1))
            sent = payload(mock["analyze_step"].stream_events.call_args.args[0])
            assert len(sent["conclusions"]) == count and sent["datasets"] == []
            assert "slots" not in sent and "question" not in sent
            with TestCase().assertRaises(ValueError):
                route_analysis({**result, "step_index": count + 2})
    for node in ("fetch_step_data", "summarize_scenario", "recommend_charts"):
        ctx, mock = context(), models()
        graph = build_analysis_graph()
        config = {"configurable": {"thread_id": node}, "recursion_limit": 100}
        if node == "fetch_step_data":
            target = ctx.query_data
            original = target.side_effect
            calls = 0
            def query(request):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise ConnectionError("模拟第二步断开")
                return original(request)
            target.side_effect = query
        else:
            target = mock[node].stream_events if node == "summarize_scenario" else mock[node].with_structured_output.return_value.invoke
            original = target.side_effect
            target.side_effect = RuntimeError("模拟失败")
        with patched_models(mock):
            graph.invoke(create_initial_state("标保"), config, context=ctx)
            with TestCase().assertRaises(RuntimeError):
                graph.invoke(Command(resume="standard_premium_review"), config, context=ctx)
            saved = graph.get_state(config)
            assert saved.next == (node,)
            if node == "fetch_step_data":
                assert len(saved.values["datasets"]) == 1 and saved.values["step_index"] == 1
            else:
                assert len(saved.values["step_results"]) == 5 and ctx.query_data.call_count == 5
                target.side_effect = original
            result = graph.invoke(None, config, context=ctx)
            assert result["summary"] and result["chart_recommendations"]
            assert ctx.query_data.call_count == (6 if node == "fetch_step_data" else 5)
    print("deterministic loops, conclusion-only steps and checkpoint recovery: PASS")

if __name__ == "__main__":
    test_analysis_loop()
