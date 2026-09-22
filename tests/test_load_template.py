"""运行：python -B tests/test_load_template.py。无需模型或网络。"""

import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from omegaconf import OmegaConf
from life_insurance_business_analysis_assistant.scenario_store import read_scenarios

from life_insurance_business_analysis_assistant.agent.context import (
    AgentContext,
    load_scenario_catalog,
)
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.state import AgentState, create_initial_state


def test_load_template():
    path = Path(__file__).resolve().parents[1] / "config/templates/Scenario"
    context = AgentContext(load_scenario_catalog(path), template_path=path)
    for scenario_id, count in [("standard_premium_review", 5), ("value_review", 3)]:
        state = create_initial_state("2026年8月标保和价值")
        state["scenario_id"] = scenario_id
        before = deepcopy(state)
        update = load_template(state, Runtime(context=context))
        assert set(update) == {"template"}
        template = update["template"]
        assert template["scenario_id"] == scenario_id
        assert [s["step_id"] for s in template["steps"]] == list(range(1, count + 1))
        assert template["slot_definitions"]["月份"]["minimum"] == 1
        assert set(template["slot_definitions"]) == {"年份", "月份"}
        assert "default" not in template["slot_definitions"]["年份"]
        assert template["steps"][0]["query_params"] == {}
        assert state == before
        json.dumps(template, ensure_ascii=False)

    original = read_scenarios(path)[0]
    state = create_initial_state("标保")
    state["scenario_id"] = "standard_premium_review"
    with TemporaryDirectory() as directory:
        sample = Path(directory) / "scenarios.yaml"
        runtime = Runtime(context=AgentContext(context.scenario_catalog, sample))

        def write(data):
            OmegaConf.save(OmegaConf.create(data), sample)

        def reject(data, message):
            write(data)
            before = deepcopy(state)
            try:
                load_template(state, runtime)
            except ValueError as error:
                assert message in str(error), str(error)
            else:
                raise AssertionError(f"未拒绝错误模板: {message}")
            assert state == before

        shuffled = deepcopy(original)
        shuffled["分析思路"].reverse()
        shuffled["输入参数"]["年份"]["默认值"] = 2026
        shuffled["分析思路"][0].pop("分析模式")
        write(shuffled)
        snapshot = load_template(state, runtime)["template"]
        assert [s["step_id"] for s in snapshot["steps"]] == [1, 2, 3, 4, 5]
        assert type(snapshot["slot_definitions"]["年份"]["default"]) is int
        assert "analysis_mode" not in snapshot["steps"][-1]
        no_data = deepcopy(original)
        no_data["分析思路"][0]["指标"] = []
        no_data["分析思路"][0].pop("取数参数", None)
        write(no_data)
        direct = load_template(state, runtime)["template"]["steps"][0]
        assert direct["metrics"] == [] and direct["query_params"] == {}
        saved = deepcopy(snapshot)
        write({})
        assert snapshot == saved  # 源文件后续修改不改变已加载快照。

        for field, value, message in [
            ("默认值", 13, "超出允许范围"),
            ("默认值", "8", "必须是整数"),
            ("默认值", True, "必须是整数"),
            ("最小值", 13, "最小值不能大于最大值"),
            ("类型", "number", "仅支持"),
            ("必填", "true", "布尔值"),
        ]:
            invalid = deepcopy(original)
            invalid["输入参数"]["月份"][field] = value
            reject(invalid, message)
        for field, value, message in [
            ("步骤序号", 2, "无重复"),
            ("步骤序号", 7, "连续递增"),
            ("步骤序号", True, "正整数"),
            ("分析步骤", "", "非空字符串"),
            ("分析步骤", "查询{{未声明}}", "未声明槽位"),
            ("指标", [""], "非空字符串"),
            ("取数参数", {"年份": "{{未知年份}}"}, "未声明槽位"),
            ("取数参数", {"年份": "{{年份}"}, "无效槽位占位符"),
            ("取数参数", {"年份": True}, "字符串或整数"),
        ]:
            invalid = deepcopy(original)
            invalid["分析思路"][0][field] = value
            reject(invalid, message)
        reject({"场景": [original] * 2}, "不支持场景合集")
        reject({"场景": []}, "不支持场景合集")
        reject({}, "单个场景")
        write(original)
        for scenario_id in (None, "unknown"):
            state["scenario_id"] = scenario_id
            reject(original, "scenario_id" if scenario_id is None else "实际找到 0 个")

    state["scenario_id"] = "standard_premium_review"
    graph = StateGraph(AgentState, context_schema=AgentContext)
    graph.add_node("load_template", load_template)
    graph.add_edge(START, "load_template")
    graph.add_edge("load_template", END)
    output = graph.compile().invoke(state, context=context)
    assert output["template"]["scenario_id"] == state["scenario_id"]
    assert output["slots"] == {} and output["step_index"] == 0


if __name__ == "__main__":
    test_load_template()
    print("load_template: PASS")
