"""python -B tests/test_fetch_step_data.py；查询提交、去重及错误不转为空数据。"""

from copy import deepcopy
from unittest import TestCase

from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.nodes.fetch_step_data import fetch_step_data
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.nodes.plan_step import plan_step
from life_insurance_business_analysis_assistant.agent.state import create_initial_state
from life_insurance_business_analysis_assistant.data_query import DataQueryError
from workflow_support import context, models, patched_models, SLOTS


def test_fetch_step_data():
    ctx, mock = context(), models()
    runtime = Runtime(context=ctx)
    state = create_initial_state("标保")
    state.update(scenario_id="standard_premium_review", slots=SLOTS)
    state.update(load_template(state, runtime))
    with patched_models(mock):
        state.update(plan_step(state, runtime))
    before = deepcopy(state)
    update = fetch_step_data(state, runtime)
    assert state == before and set(update) == {"datasets"}
    assert len(update["datasets"]) == 1
    assert next(iter(update["datasets"].values()))["data"]["rows"][0]["标保达成"] == 12444
    state.update(update)
    assert fetch_step_data(state, runtime) == {} and ctx.query_data.call_count == 1
    wrong_unit = deepcopy(next(iter(update["datasets"].values())))
    wrong_unit["units"]["标保达成"] = "元"
    state = before
    for response in (wrong_unit, None, {"rows": []}, {"value": float("nan")}):
        ctx.query_data.side_effect = None
        ctx.query_data.return_value = response
        with TestCase().assertLogs("life_insurance_business_analysis_assistant.agent.nodes.fetch_step_data", level="ERROR"):
            try:
                fetch_step_data(state, runtime)
            except DataQueryError:
                pass
            else:
                raise AssertionError("非法响应不能继续分析")
        assert state == before
    print("fetch response validation, deduplication and failure isolation: PASS")


if __name__ == "__main__":
    test_fetch_step_data()
