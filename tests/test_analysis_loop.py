"""python -B tests/test_analysis_loop.py；循环、无数据步骤与查询/总结/图表失败恢复。"""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from langgraph.types import Command
from omegaconf import OmegaConf
from life_insurance_business_analysis_assistant.scenario_store import read_scenarios

from life_insurance_business_analysis_assistant.agent.graph import build_analysis_graph, route_analysis
from life_insurance_business_analysis_assistant.agent.state import create_initial_state
from life_insurance_business_analysis_assistant.data_query import DataQueryError
from workflow_support import TEMPLATE, context, models, patched_models, payload


def test_analysis_loop():
    raw = read_scenarios(TEMPLATE)
    with TemporaryDirectory() as directory:
        path = Path(directory) / "scenario.yaml"
        for count in (1, 3, 15):
            source = deepcopy(raw[0])
            first = source["分析思路"][0]
            source["分析思路"] = [{**deepcopy(first), "步骤序号": i + 1} for i in range(count)]
            source["分析思路"].append({"步骤序号": count + 1, "分析步骤": "综合前序结论", "指标": []})
            OmegaConf.save(OmegaConf.create(source), path)
            ctx, mock = context(path), models()
            planner = mock["plan_step"].with_structured_output.return_value.invoke
            original = planner.side_effect
            def plan(messages, **kwargs):
                intent = original(messages, **kwargs)
                for item in intent["requirements"]:
                    item["grain"] = "system"
                return intent
            planner.side_effect = plan
            graph = build_analysis_graph()
            config = {"configurable": {"thread_id": f"loop-{count}"}, "recursion_limit": 200}
            with patched_models(mock):
                graph.invoke(create_initial_state("2026年8月个险全系统标保"), config, context=ctx)
                result = graph.invoke(Command(resume="standard_premium_review"), config, context=ctx)
            assert ctx.query_data.call_count == 1
            assert result["step_index"] == len(result["step_results"]) == count + 1
            assert result["step_results"][-1]["data_uses"] == []
            assert result["step_results"][-1]["conclusion_step_ids"] == list(range(1, count + 1))
            assert len(payload(mock["analyze_step"].stream_events.call_args.args[0])["conclusions"]) == count
            try:
                route_analysis({**result, "step_index": count + 2})
            except ValueError:
                pass
            else:
                raise AssertionError("越界不能当作完成")
    for failure_node in ("fetch_step_data", "summarize_scenario", "recommend_charts"):
        ctx, mock = context(), models()
        graph = build_analysis_graph()
        config = {"configurable": {"thread_id": failure_node}, "recursion_limit": 100}
        if failure_node == "fetch_step_data":
            # 第一步分成两个独立需求，第二项失败不能丢掉第一项成功查询。
            planner = mock["plan_step"].with_structured_output.return_value.invoke
            original_plan = planner.side_effect
            def split(messages, **kwargs):
                intent = original_plan(messages, **kwargs)
                if payload(messages)["step"]["step_id"] == 1:
                    item = intent["requirements"][0]
                    intent["requirements"] = [{**item, "metrics": item["metrics"][:2]}, {**item, "metrics": item["metrics"][2:]}]
                return intent
            planner.side_effect = split
            target = ctx.query_data
            original = target.side_effect
            calls = 0
            def query(request):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise ConnectionError("模拟第二项查询断开")
                return original(request)
            target.side_effect = query
        else:
            target = mock[failure_node].stream_events if failure_node == "summarize_scenario" else mock[failure_node].with_structured_output.return_value.invoke
            original = target.side_effect
            target.side_effect = RuntimeError("模拟失败")
        with patched_models(mock):
            graph.invoke(create_initial_state("2026年8月个险全系统标保"), config, context=ctx)
            logs = TestCase().assertLogs("life_insurance_business_analysis_assistant.agent.nodes.fetch_step_data", level="ERROR") if failure_node == "fetch_step_data" else None
            if logs:
                logs.__enter__()
            try:
                graph.invoke(Command(resume="standard_premium_review"), config, context=ctx)
            except (RuntimeError, DataQueryError):
                pass
            else:
                raise AssertionError("应当保留失败节点")
            finally:
                if logs:
                    logs.__exit__(None, None, None)
            saved = graph.get_state(config)
            assert saved.next == (failure_node,)
            if failure_node == "fetch_step_data":
                assert len(saved.values["datasets"]) == 1 and saved.values["step_index"] == 0
            else:
                assert len(saved.values["step_results"]) == 5 and ctx.query_data.call_count == 3
                target.side_effect = original
            result = graph.invoke(None, config, context=ctx)
            assert result["summary"] and result["chart_recommendations"]
            assert ctx.query_data.call_count == (5 if failure_node == "fetch_step_data" else 3)
    print("analysis loops, conclusion-only steps and query/summary/chart recovery: PASS")


if __name__ == "__main__":
    test_analysis_loop()
