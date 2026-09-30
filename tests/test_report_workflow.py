"""离线检查报告分支、模板校验、失败恢复；运行 python -B tests/test_report_workflow.py。"""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import yaml
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.graph import build_chat_graph
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.nodes.load_report_template import load_report_template
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.rendering import display_value
from life_insurance_business_analysis_assistant.data_query import DataQueryError
from workflow_support import context, models, patched_models, payload, query_fixture


REPORTS = Path(__file__).resolve().parents[1] / "config/templates/Report"
CODE = "Monthly_Business_Review"


def test_report():
    ctx = replace(context(), report_template_path=REPORTS)
    mock = models()
    graph = build_chat_graph(studio_context=ctx).builder.compile(checkpointer=InMemorySaver())
    graph.get_input_jsonschema()
    graph.get_output_jsonschema()
    config = {"configurable": {"thread_id": "report"}}
    question = "生成一份月度经营分析报告"  # 无年月和范围，仍应直接执行。
    with patched_models(mock):
        events = list(graph.stream({"question": question, "report_template_id": CODE}, config,
                                   context={}, stream_mode=["values", "custom"], subgraphs=True))
        result = graph.get_state(config).values
        names = {name for name, _ in graph.get_subgraphs()}
        assert names == {"question_answer", "report_generation"}
        custom = [data for _, kind, data in events if kind == "custom"]
        snapshots = [e["report"] for e in custom if e.get("type") == "report_snapshot"]
        assert len(snapshots) == 11  # 章节初始化 + 8 次提交 + 图表 + 完成。
        assert snapshots[0]["status"] == "generating" and snapshots[0]["revision"] == 0
        assert all(not block["text"] for section in snapshots[0]["sections"] for block in section["blocks"])
        assert custom.index(next(e for e in custom if e["type"] == "report_snapshot")) < custom.index(next(e for e in custom if e["type"] == "report_step"))
        assert not any(e.get("type") == "analysis_delta" for e in custom)
        assert [s["section_id"] for s in snapshots[0]["sections"]] == [s["section_id"] for s in snapshots[-1]["sections"]]
        assert all(block["status"] == "complete" for section in snapshots[-1]["sections"] for block in section["blocks"])
        assert len([m for m in result["messages"] if m.id.endswith(":report")]) == 1
        assert not any(":step:" in m.id or m.id.endswith(":charts") for m in result["messages"])
        assert result["status"] == "已完成" and "__interrupt__" not in result
        assert ctx.query_data.call_count == 7
        assert mock["analyze_step"].stream_events.call_count == 8
        mock["match_scenario"].with_structured_output.assert_not_called()
        mock["summarize_scenario"].stream_events.assert_not_called()
        assert result["summary"] is None
        requests = [c.args[0] for c in ctx.query_data.call_args_list]
        assert all(r.question == question and r.reportInfo.report_id == CODE and r.scenarioInfo is None for r in requests)
        assert requests[0].guidance == [] and requests[1].guidance
        assert requests[1].section_path == ["人力概况", "活动人力"]
        summary = payload(mock["analyze_step"].stream_events.call_args_list[-1].args[0])
        assert summary["datasets"] == [] and len(summary["conclusions"]) == 7
        assert summary["writing_style"]["单位规则"] and summary["report"]
        report = result["report_result"]
        assert [s["section_id"] for s in report["sections"]] == ["1", "2", "2.1", "2.2", "3"]
        assert report["sections"][1]["body"] == ""
        assert report["sections"][-1]["body"] == "模拟步骤结论-8"
        assert "# 月度经营分析" in report["markdown"] and "数据说明" in report["markdown"]
        assert report["chart_recommendations"][0]["section_id"] == "2.1"
        assert any(m.id.endswith(":report") for m in result["messages"])
        # 同线程显式取消模板，回到智能问答且清空报告产物。
        result = graph.invoke({"question": "标保", "report_template_id": None}, config, context={})
        assert "__interrupt__" in result and result["report_result"] is None
        assert result["report_id"] is None
    print("report routing, context, template summary, assembly, chat reset: PASS")


def test_template_and_resume():
    raw = yaml.safe_load((REPORTS / f"{CODE}.yaml").read_text(encoding="utf-8"))
    with TemporaryDirectory() as directory:
        file = Path(directory) / f"{CODE}.yaml"
        def write(value):
            file.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")
        ctx = replace(context(), report_template_path=directory)
        state = {"report_template_id": CODE, "question": "月报"}
        invalid = deepcopy(raw)
        invalid["章节板块"][1]["关联指标"] = ["错误的父级指标"]
        write(invalid)
        with TestCase().assertRaises(ValueError):
            load_report_template(state, Runtime(context=ctx))
        invalid = deepcopy(raw)
        invalid["章节板块"][1]["子板块"][0]["分析步骤"][0]["步骤序号"] = 2
        write(invalid)
        with TestCase().assertRaises(ValueError):
            load_report_template(state, Runtime(context=ctx))
        # 去掉总结；同名子板块仍按位置区分。
        raw["章节板块"].pop()
        raw["章节板块"][1]["子板块"][1]["子板块名称"] = "活动人力"
        write(raw)
        queries = []
        fail = True
        def query(request):
            nonlocal fail
            queries.append(request.step.step_id)
            if request.step.step_id == 3 and fail:
                fail = False
                raise TimeoutError("模拟故障")
            return query_fixture(request)
        ctx = replace(ctx, query_data=query)
        graph = build_chat_graph(studio_context=ctx).builder.compile(checkpointer=InMemorySaver())
        mock = models()
        config = {"configurable": {"thread_id": "resume"}}
        with patched_models(mock):
            with TestCase().assertRaises(DataQueryError):
                graph.invoke({"question": "月报", "report_template_id": CODE}, config)
            assert graph.get_state(config).values.get("report_result") is None
            child = graph.get_state(config, subgraphs=True).tasks[0].state
            assert child.values["step_index"] == 2
            assert child.values["report_result"]["revision"] == 2
            assert child.values["report_result"]["sections"][0]["blocks"][0]["status"] == "complete"
            assert child.values["report_result"]["status"] == "generating"
            # 模板文件在失败期间改变，不影响已加载快照。
            file.write_text("invalid", encoding="utf-8")
            result = graph.invoke(None, config)
            assert queries == [1, 2, 3, 3, 4, 5, 6, 7]
            assert mock["analyze_step"].stream_events.call_count == 7
            mock["summarize_scenario"].stream_events.assert_not_called()
            assert len(result["report_result"]["sections"]) == 4
            assert [s["section_id"] for s in result["template"]["steps"]][1:] == ["2.1"] * 3 + ["2.2"] * 3
    assert display_value(12345, "元", "金额单位万元；百分比保留1位小数") == ("1.2345", "万元")
    assert display_value(61.85, "%", "百分比保留1位小数") == ("61.9", "%")
    assert display_value(1, None, "金额单位万元")[1] is None
    print("template validation, no extra summary, frozen snapshot and retry: PASS")


def test_commit_retry():
    from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.presentation import publish_report
    ctx, mock = replace(context(), report_template_path=REPORTS), models()
    graph = build_chat_graph(studio_context=ctx).builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "commit-retry"}}
    fail = True

    def publish(state, **kwargs):
        nonlocal fail
        if len(state["step_results"]) == 1 and fail:
            fail = False
            raise RuntimeError("模拟章节提交故障")
        return publish_report(state, **kwargs)

    with patched_models(mock), patch("life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.nodes.commit_report_step.publish_report", side_effect=publish):
        with TestCase().assertRaises(RuntimeError):
            graph.invoke({"question": "月报", "report_template_id": CODE}, config)
        child = graph.get_state(config, subgraphs=True).tasks[0].state
        assert child.next == ("commit_report_step",)
        assert child.values["pending_result"]["step_id"] == 1
        result = graph.invoke(None, config)
        assert ctx.query_data.call_count == 7 and mock["analyze_step"].stream_events.call_count == 8
        assert result["report_result"]["status"] == "complete"
    print("commit failure resumes without rerunning model or query: PASS")


if __name__ == "__main__":
    test_report()
    test_template_and_resume()
    test_commit_retry()
