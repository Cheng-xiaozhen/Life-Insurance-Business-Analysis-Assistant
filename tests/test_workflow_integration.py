"""运行：python -B tests/test_workflow_integration.py；真实整图、Fake 查询和模拟 LLM。"""

import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, call, patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.types import Command
from langgraph.checkpoint.memory import InMemorySaver

from life_insurance_business_analysis_assistant.agent.context import AgentContext, load_scenario_catalog
from life_insurance_business_analysis_assistant.agent.graph import build_graph
from life_insurance_business_analysis_assistant.agent.state import create_initial_state
from life_insurance_business_analysis_assistant.data_query import make_fake_query


def test_workflow_integration(studio=False):
    path = Path(__file__).resolve().parents[1] / "config/templates/Scenario/场景分析模板.yaml"
    slots = {"年份": 2026, "月份": 8, "渠道": "个险", "机构范围": "全系统"}
    complete = {"年份": 2026, "月份": 8}
    # 同时覆盖选择场景后仍需补参的连续两种追问。
    cases = [
        ("single", "2026年8月标保", [complete], [], "standard_premium_review"),
        ("slots", "2026年标保", [{"年份": 2026}, {"月份": 8}],
         [("slot_completion", "8月")], "standard_premium_review"),
        ("choice", "2026年8月标保和价值", [complete],
         [("scenario_selection", "value_review")], "value_review"),
        ("both", "标保和价值", [{}, complete],
         [("scenario_selection", "standard_premium_review"),
          ("slot_completion", "2026年8月")], "standard_premium_review"),
        ("zero", "人力情况", [], [], None),
    ]
    for name, question, extractions, replies, scenario_id in cases:
        extractor, analyzer, summarizer, charts = Mock(), Mock(), Mock(), Mock()
        extract = extractor.with_structured_output.return_value.invoke
        extract.side_effect = [{"values": values, "ambiguous": {}} for values in extractions]
        analysis_inputs, summary_inputs = [], []

        def analyze(messages, **kwargs):
            payload = json.loads(messages[1][1])
            analysis_inputs.append(payload)
            assert set(payload) == {"scenario", "step", "slots", "current_data"}
            conclusion = f"模拟步骤结论-{payload['step']['step_id']}"
            return FakeListChatModel(responses=[conclusion]).stream_events(messages, **kwargs)

        def summarize(messages, **kwargs):
            payload = json.loads(messages[1][1])
            summary_inputs.append(payload)
            assert set(payload) == {"scenario", "slots", "conclusions"}
            return FakeListChatModel(responses=["模拟场景整体总结"]).stream_events(messages, **kwargs)

        analyzer.stream_events.side_effect = analyze
        summarizer.stream_events.side_effect = summarize
        decision = {"recommended": False, "chart_type": None, "step_id": 1,
                    "dimensions": [], "metrics": [], "reason": "首步只有一条总体记录",
                    "description": "直接阅读模拟分析结论"}
        chart_invoke = charts.with_structured_output.return_value.invoke
        chart_invoke.return_value = decision
        fake = make_fake_query(slots)
        query = Mock(side_effect=fake)
        context = AgentContext(load_scenario_catalog(path), path, query)
        graph = build_graph(studio_context=context) if studio else build_graph()
        if studio:
            # 模拟 Agent Server 注入检查点，并验证 Studio 所需的 Schema。
            graph.get_input_jsonschema()
            graph.get_output_jsonschema()
            graph = graph.builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": name}}
        order = []

        def run(value):
            updates = list(graph.stream(value, config, context=context, stream_mode="updates"))
            order.extend(node for update in updates for node in update if node != "__interrupt__")
            return [item for update in updates for item in update.get("__interrupt__", ())]

        with ExitStack() as stack:
            getters = [stack.enter_context(patch(
                f"life_insurance_business_analysis_assistant.agent.nodes.{node}.get_llm",
                return_value=model,
            )) for node, model in [("resolve_slots", extractor), ("analyze_step", analyzer),
                                  ("summarize_scenario", summarizer), ("recommend_charts", charts)]]
            interrupts = run({"question": question} if studio else create_initial_state(question))
            for kind, reply in replies:
                assert len(interrupts) == 1 and interrupts[0].value["kind"] == kind
                paused = graph.get_state(config).values
                assert paused["step_results"] == [] and paused["summary"] is None
                query.assert_not_called()
                interrupts = run(Command(resume=reply))
            assert not interrupts
            snapshot = graph.get_state(config)
            result = snapshot.values
            assert snapshot.next == () and result["question"] == question
            assert result["clarification"] is None and result["user_reply"] is None
            assert result["current_data"] is None and result["scenario_id"] == scenario_id
            if scenario_id is None:
                assert order == ["match_scenario"]
                assert result["slots"] == {} and result["step_results"] == []
                assert result["template"] is None and result["summary"] is None
                assert result["chart_recommendations"] is None
                query.assert_not_called()
                for getter in getters:
                    getter.assert_not_called()
                print(f"workflow {name}: PASS")
                continue

            steps = result["template"]["steps"]
            expected_order = ["match_scenario"]
            if replies and replies[0][0] == "scenario_selection":
                expected_order.append("clarify")
            expected_order += ["load_template", "resolve_slots"]
            if any(kind == "slot_completion" for kind, _ in replies):
                expected_order += ["clarify", "resolve_slots"]
            expected_order += ["fetch_step_data", "analyze_step"] * len(steps)
            expected_order += ["summarize_scenario", "recommend_charts"]
            assert order == expected_order, (name, order)
            assert result["slots"] == slots and result["step_index"] == len(steps)
            assert query.call_args_list == [call(step["metrics"], slots) for step in steps]
            expected_results = [{"step_id": step["step_id"], "data": fake(step["metrics"], slots),
                                 "conclusion": f"模拟步骤结论-{step['step_id']}"} for step in steps]
            assert result["step_results"] == expected_results
            for payload, step, saved in zip(analysis_inputs, steps, expected_results, strict=True):
                assert payload["step"]["step_id"] == step["step_id"]
                assert payload["current_data"] == saved["data"] and payload["slots"] == slots
            assert len(summary_inputs) == 1
            assert summary_inputs[0]["conclusions"] == [
                {"step_id": r["step_id"], "conclusion": r["conclusion"]} for r in expected_results]
            assert summary_inputs[0]["slots"] == slots
            assert result["summary"] == "模拟场景整体总结"
            chart_invoke.assert_called_once()
            chart_input = json.loads(chart_invoke.call_args.args[0][1][1])
            assert chart_input["data"] == expected_results[0]["data"]
            assert chart_input["conclusion"] == expected_results[0]["conclusion"]
            assert chart_input["step"]["step_id"] == 1
            assert result["chart_recommendations"] == [decision]
            assert extract.call_count == len(extractions)
            for getter, thinking in zip(getters, [False, True, True, True], strict=True):
                assert getter.call_args_list and all(
                    item == call(thinking=thinking) for item in getter.call_args_list
                )
            assert extractor.with_structured_output.call_args.kwargs == {"method": "function_calling"}
            assert charts.with_structured_output.call_args.kwargs == {"method": "json_mode"}
            if len(extractions) > 1:
                last_input = json.loads(extract.call_args.args[0][1][1])
                assert last_input["question"] == question
                assert last_input["user_reply"] == replies[-1][1]
        print(f"workflow {name}: PASS")


if __name__ == "__main__":
    test_workflow_integration()
    test_workflow_integration(studio=True)
