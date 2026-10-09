"""前序多表引用、范围隔离和各消费边界的离线回归。"""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import yaml
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from life_insurance_business_analysis_assistant.agent.graph import build_chat_graph
from life_insurance_business_analysis_assistant.agent.shared.charts import chart_candidates
from life_insurance_business_analysis_assistant.agent.shared.execution import (
    finalize_execution,
    generate_step_result,
)
from life_insurance_business_analysis_assistant.agent.subgraphs.question_answer.nodes.summarize_scenario import summarize_scenario
from life_insurance_business_analysis_assistant.agent.subgraphs.report_generation.rendering import build_report
from workflow_support import context, models, patched_models, payload, query_fixture


def test_prior_data():
    source = Path(__file__).resolve().parents[1] / "config/templates/Report/Monthly_Business_Review.yaml"
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    child = raw["章节板块"][1]["子板块"][0]
    local = deepcopy(child["分析步骤"][-1])
    local.update(步骤序号=len(child["分析步骤"]) + 1, 分析步骤="综合分析本板块", 关联指标=[])
    child["分析步骤"].append(local)

    def query(request):
        result = query_fixture(request)
        if request.step.step_id == 2:
            result.datasets.append(result.datasets[0].model_copy(deep=True))
        return result

    with TemporaryDirectory() as directory:
        Path(directory, source.name).write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
        ctx = replace(context(), report_template_path=directory)
        ctx.query_data.side_effect = query
        mock = models()
        graph = build_chat_graph(studio_context=ctx).builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "prior-data"}, "recursion_limit": 100}
        with patched_models(mock):
            state = graph.invoke({"question": "月报", "report_template_id": "Monthly_Business_Review"}, config)
        steps = state["template"]["steps"]
        local_step = next(s for s in steps if s["section_id"] == "2.1" and not s["metrics"])
        index = local_step["step_id"] - 1
        sent = payload(mock["analyze_step"].stream_events.call_args_list[index].args[0])
        local_ids = ["step:2:table:1", "step:2:table:2", "step:3:table:1", "step:4:table:1"]
        assert [d["dataset_id"] for d in sent["datasets"]] == local_ids
        assert [c["step_id"] for c in sent["conclusions"]] == [2, 3, 4]
        analysis = state["analysis_result"]
        assert analysis["step_results"][index]["dataset_ids"] == local_ids
        assert ctx.query_data.call_count == 7
        final_payload = payload(mock["analyze_step"].stream_events.call_args.args[0])
        assert len(final_payload["datasets"]) == len(analysis["datasets"]) == 8
        assert len(chart_candidates(state)) == 8
        assert all(c["step_id"] != local_step["step_id"] for c in chart_candidates(state))
        section = next(s for s in state["report_result"]["sections"] if s["section_id"] == "2.1")
        assert section["dataset_ids"] == local_ids
        assert section["table_markdown"].count("数据说明：") == 4

        # 只引用一个已完成综合步骤时，仍保留它的数据真实来源。
        inherited = {**state, **deepcopy(analysis), "step_index": len(steps) - 1,
                     "current_step": {**steps[-1], "source_step_ids": [local_step["step_id"]]}}
        inherited["step_results"] = inherited["step_results"][:-1]
        with patched_models(mock):
            outcome = generate_step_result(inherited, {}, stream=lambda *args: (
                "综合结论", AIMessage(content="综合结论")
            ))
        assert outcome["dataset_ids"] == local_ids

        # 对所有消费入口注入越界、未来、缺失或重复引用，不能被图表去重掩盖。
        for wrong in (["step:1:table:1"], ["step:6:table:1"], ["missing"], local_ids * 2):
            invalid = deepcopy(state)
            invalid["analysis_result"]["step_results"][index]["dataset_ids"] = wrong
            execution = {**invalid, **invalid["analysis_result"], "step_index": len(steps)}
            for consume in (
                lambda: finalize_execution(execution),
                lambda: chart_candidates(invalid),
                lambda: build_report(invalid, complete=True),
                lambda: summarize_scenario({**invalid, "clarification": None}, {}),
            ):
                with TestCase().assertRaises(ValueError):
                    consume()

        # 生成前重验原请求和数据，不能引用尚未完成步骤或带入损坏快照。
        execution = {**state, **deepcopy(analysis), "step_index": index, "current_step": local_step}
        execution["step_results"] = execution["step_results"][:index]
        for change in ("future", "request", "payload"):
            invalid = deepcopy(execution)
            if change == "future":
                invalid["current_step"]["source_step_ids"] = [len(steps)]
            elif change == "request":
                invalid["datasets"][local_ids[0]]["request"]["question"] = "另一任务"
            else:
                invalid["datasets"][local_ids[0]]["payload"]["units"] = {}
            with TestCase().assertRaises(ValueError):
                generate_step_result(invalid, {})
    print("prior multi-table evidence, section scope, provenance and consumer validation: PASS")


if __name__ == "__main__":
    test_prior_data()
