"""运行：python -B tests/test_analysis_loop.py；验证循环边界及失败恢复。"""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from omegaconf import OmegaConf

from life_insurance_business_analysis_assistant.agent.context import AgentContext, load_scenario_catalog
from life_insurance_business_analysis_assistant.agent.graph import build_graph, route_analysis
from life_insurance_business_analysis_assistant.agent.state import create_initial_state
from life_insurance_business_analysis_assistant.data_query import make_fake_query


@patch("life_insurance_business_analysis_assistant.agent.nodes.recommend_charts.get_llm")
@patch("life_insurance_business_analysis_assistant.agent.nodes.summarize_scenario.get_llm", return_value=FakeListChatModel(responses=["模拟场景总结"]))
def test_analysis_loop(summary_llm, chart_llm):
    chart_model = Mock()
    chart_model.with_structured_output.return_value.invoke.return_value = {"recommended": False, "chart_type": None, "step_id": 1, "dimensions": [], "metrics": [], "reason": "数据不足", "description": "阅读结论"}
    chart_llm.return_value = chart_model
    path = Path(__file__).resolve().parents[1] / "config/templates/Scenario/场景分析模板.yaml"
    raw = OmegaConf.to_container(OmegaConf.load(path), resolve=False)
    slots = {"年份": 2026, "月份": 8, "渠道": "个险", "机构范围": "全系统"}
    with TemporaryDirectory() as directory:
        sample = Path(directory) / "scenario.yaml"
        for count in (1, 3, 15):
            template = deepcopy(raw["场景"][0])
            step = template["分析思路"][0]
            template["分析思路"] = [{**deepcopy(step), "步骤序号": i + 1} for i in range(count)]
            OmegaConf.save(OmegaConf.create({"场景": [template]}), sample)
            calls, prompts = [], []

            def query(metrics, params):
                calls.append(list(metrics))
                return {"is_mock": True, "marker": f"data-{len(calls)}"}

            model = Mock()
            fail_once = count == 3

            def stream(messages, **kwargs):
                nonlocal fail_once
                payload = json.loads(messages[1][1])
                index = payload["step"]["step_id"]
                prompts.append(payload)
                assert payload["current_data"]["marker"] == f"data-{index}"
                assert set(payload) == {"scenario", "step", "slots", "current_data"}
                if index == 2 and fail_once:
                    fail_once = False
                    raise RuntimeError("模拟第二步失败")
                return FakeListChatModel(responses=[f"conclusion-{index}"]).stream_events(messages, **kwargs)

            model.stream_events.side_effect = stream
            extractor = Mock()
            extractor.with_structured_output.return_value.invoke.return_value = {"values": slots, "ambiguous": {}}
            context = AgentContext(load_scenario_catalog(sample), sample, query)
            config = {"configurable": {"thread_id": f"loop-{count}"}, "recursion_limit": 2 * count + 10}
            with patch("life_insurance_business_analysis_assistant.agent.nodes.resolve_slots.get_llm", return_value=extractor), \
                 patch("life_insurance_business_analysis_assistant.agent.nodes.analyze_step.get_llm", return_value=model):
                graph = build_graph()
                try:
                    result = graph.invoke(create_initial_state("标保"), config, context=context)
                except RuntimeError as error:
                    assert count == 3 and "模拟第二步失败" in str(error)
                    saved = graph.get_state(config).values
                    assert saved["step_index"] == 1 and len(saved["step_results"]) == 1
                    assert len(calls) == 2
                    result = graph.invoke(None, config, context=context)
                assert len(calls) == count
                assert [r["step_id"] for r in result["step_results"]] == list(range(1, count + 1))
                assert [r["conclusion"] for r in result["step_results"]] == [f"conclusion-{i}" for i in range(1, count + 1)]
                assert result["step_index"] == count and result["current_data"] is None
                assert result["summary"] == "模拟场景总结" and result["chart_recommendations"][0]["recommended"] is False
                assert graph.get_state(config).next == ()
                assert len(prompts) == count + (1 if count == 3 else 0)
                result["step_index"] = count + 1
                try:
                    route_analysis(result)
                except ValueError:
                    pass
                else:
                    raise AssertionError("越界索引不能作为完成")

    fake = make_fake_query(slots)
    for metric, threshold, expected in (("标保达成率", 70, 9), ("全年标保进度", 60, 7), ("价值达成率", 85, 5)):
        data = fake([metric], slots)
        assert sum(float(r[metric].rstrip("%")) > threshold for r in data["rows"]) == expected
        data["rows"].clear()
        assert fake([metric], slots)["rows"]  # 相同指标仍返回独立响应。


if __name__ == "__main__":
    test_analysis_loop()
    print("analysis loop: PASS")
