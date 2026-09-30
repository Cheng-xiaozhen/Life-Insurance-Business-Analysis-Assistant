"""离线检查报告分支、模板校验、失败恢复；运行 python -B tests/test_report_workflow.py。"""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import yaml
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.graph import build_chat_graph
from life_insurance_business_analysis_assistant.agent.nodes.report import load_report_template, display_value
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
        result = graph.invoke({"question": question, "report_template_id": CODE}, config)
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
        result = graph.invoke({"question": "标保", "report_template_id": None}, config)
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


if __name__ == "__main__":
    test_report()
    test_template_and_resume()
