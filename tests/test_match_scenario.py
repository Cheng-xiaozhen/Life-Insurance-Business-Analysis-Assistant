"""运行：python -B tests/test_match_scenario.py。模型为显式模拟，不访问网络。"""

from copy import deepcopy
from unittest.mock import patch
from workflow_support import models, patched_models
from pathlib import Path
from tempfile import TemporaryDirectory

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from omegaconf import OmegaConf

from life_insurance_business_analysis_assistant.agent.context import (
    AgentContext,
    load_scenario_catalog,
)
from life_insurance_business_analysis_assistant.agent.nodes.match_scenario import match_scenario
from life_insurance_business_analysis_assistant.agent.state import AgentState, create_initial_state


def check_match_scenario():
    path = Path(__file__).resolve().parents[1] / "config/templates/Scenario"
    catalog = load_scenario_catalog(path)
    context = AgentContext(catalog)
    runtime = Runtime(context=context)
    for question, ids, scores in [
        ("人力情况", [], []),
        ("标保达成率，标保达成率", ["standard_premium_review"], [3.0]),
        ("价值达成率和标保", ["standard_premium_review", "value_review"], [1.0, 3.0]),
        ("价值和标保", ["standard_premium_review", "value_review"], [1.0, 1.0]),
    ]:
        state = create_initial_state(question)
        state["scenario_id"] = "stale"
        state["clarification"] = {"kind": "slot_completion", "prompt": "旧追问", "slot_issues": []}
        before = deepcopy(state)
        result = match_scenario(state, runtime)
        assert state == before
        assert [c["scenario_id"] for c in result["candidates"]] == ids
        assert [c["score"] for c in result["candidates"]] == scores
        assert result["scenario_id"] is None
        assert (result["clarification"] is not None) == bool(ids)

    with TemporaryDirectory() as directory:
        sample = Path(directory) / "catalog.yaml"
        entry = {"场景编码": "a", "场景名称": "场景 A", "触发关键词": [" 标保 ", "标保"]}
        OmegaConf.save(OmegaConf.create(entry), sample)
        assert load_scenario_catalog(sample)[0]["keywords"] == ["标保"]
        for invalid in [
            {}, {"场景": {}}, {"场景": [None]}, {"场景": [entry, entry]},
            {**entry, "触发关键词": [""]},
            {**entry, "触发关键词": [1]},
            {**entry, "场景编码": " "},
            {**entry, "场景名称": None},
        ]:
            OmegaConf.save(OmegaConf.create(invalid), sample)
            try:
                load_scenario_catalog(sample)
            except ValueError:
                pass
            else:
                raise AssertionError(f"未拒绝无效目录: {invalid}")

    graph = StateGraph(AgentState, context_schema=AgentContext)
    graph.add_node("match_scenario", match_scenario)
    graph.add_edge(START, "match_scenario")
    graph.add_edge("match_scenario", END)
    output = graph.compile().invoke(create_initial_state("标保"), context=context)
    assert output["scenario_id"] is None and output["clarification"]["kind"] == "scenario_selection"
    assert output["question"] == "标保"
    assert output["template"] is None


def test_match_scenario():
    with patched_models(models()):
        check_match_scenario()


if __name__ == "__main__":
    test_match_scenario()
    print("match_scenario: PASS")
