"""请求边界、多表原子提交、重复执行与失败隔离。"""
from workflow_support import execution_state
from copy import deepcopy
from unittest import TestCase
from langgraph.runtime import Runtime
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.fetch_step_data import fetch_step_data, build_request
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.state import create_initial_state
from life_insurance_business_analysis_assistant.data_query import DataQueryError
from workflow_support import context


def test_fetch_step_data():
    ctx = context()
    runtime = Runtime(context=ctx)
    state = create_initial_state("用户的私有问题：2026年8月北京银保")
    state.update(scenario_id="standard_premium_review")
    state.update(load_template(state, runtime))
    state = execution_state(state["template"])
    request = build_request(state)
    assert set(request.model_dump()) == {"scenarioInfo", "step", "metrics"}
    assert set(request.scenarioInfo.model_dump()) == {"scenario_id", "name", "channel_type", "time_dimension", "analysis_object", "analysis_purpose"}
    assert request.scenarioInfo.channel_type == "个险"
    assert "2026" not in request.model_dump_json() and "北京" not in request.model_dump_json()
    before = deepcopy(state)
    update = fetch_step_data(state, runtime)
    assert state == before and set(update) == {"datasets"}
    state.update(update)
    assert fetch_step_data(state, runtime) == {} and ctx.query_data.call_count == 1
    original = next(iter(update["datasets"].values()))["payload"]
    # 同一请求可返回多个表，先拆开测试观测，不生成新业务值。
    tables = []
    for metrics in (request.metrics[:2], request.metrics[2:]):
        tables.append({**original, "metrics": metrics, "units": {m: original["units"][m] for m in metrics},
                       "rows": [{m: row[m] for m in metrics} for row in original["rows"]]})
    ctx.query_data.side_effect = None
    ctx.query_data.return_value = {"datasets": tables}
    update = fetch_step_data(before, runtime)
    assert len(update["datasets"]) == 2 and before["datasets"] == {}
    bad = deepcopy(tables)
    bad[1]["rows"][0][request.metrics[-1]] = float("nan")
    for response in (None, {"datasets": []}, {"datasets": bad}, {"datasets": [tables[0]]}):
        ctx.query_data.return_value = response
        with TestCase().assertLogs("life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.fetch_step_data", level="ERROR"):
            with TestCase().assertRaises(DataQueryError):
                fetch_step_data(before, runtime)
        assert before["datasets"] == {} and before["step_index"] == 0
    changed = deepcopy(state)
    changed["template"]["steps"][0]["text"] += "改变请求"
    with TestCase().assertLogs("life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.fetch_step_data", level="ERROR"):
        with TestCase().assertRaises(DataQueryError):
            fetch_step_data(changed, runtime)
    print("request whitelist, multi-table atomic save, retry and isolation: PASS")

if __name__ == "__main__":
    test_fetch_step_data()
