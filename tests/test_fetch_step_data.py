"""运行：python -B tests/test_fetch_step_data.py。"""

from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.nodes.fetch_step_data import fetch_step_data
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.state import create_initial_state
from life_insurance_business_analysis_assistant.data_query import DataQueryError, make_fake_query


def test_fetch_step_data():
    path = Path(__file__).resolve().parents[1] / "config/templates/Scenario/场景分析模板.yaml"
    state = create_initial_state("标保")
    state["scenario_id"] = "standard_premium_review"
    state.update(load_template(state, Runtime(context=AgentContext([], path))))
    state["slots"] = {"年份": 2026, "月份": 8, "渠道": "个险", "机构范围": "全系统"}
    fake = make_fake_query(state["slots"])
    query = Mock(side_effect=fake)
    runtime = Runtime(context=AgentContext([], path, query))
    before = deepcopy(state)
    result = fetch_step_data(state, runtime)
    assert set(result) == {"current_data"} and state == before
    assert result["current_data"]["rows"][0]["标保达成"] == 12444
    assert result["current_data"]["is_mock"] is True
    query.assert_called_once_with(state["template"]["steps"][0]["metrics"], state["slots"])
    result["current_data"]["rows"][0]["标保达成"] = 0
    assert fetch_step_data(state, runtime)["current_data"]["rows"][0]["标保达成"] == 12444

    params = state["template"]["steps"][0]["query_params"]
    params["期间"] = "{{年份}}年{{月份}}月"
    params["常量"] = 10
    query.side_effect = None
    query.return_value = {"rows": []}
    fetch_step_data(state, runtime)
    sent = query.call_args.args[1]
    assert sent["期间"] == "2026年8月" and type(sent["年份"]) is int and sent["常量"] == 10

    for change in ("index", "missing", "clarification", "reference"):
        invalid = deepcopy(state)
        if change == "index": invalid["step_index"] = -1
        elif change == "missing": invalid["slots"].pop("年份")
        elif change == "clarification":
            invalid["clarification"] = {"kind": "slot_completion", "prompt": "年份?", "slot_issues": []}
        else: invalid["template"]["steps"][0]["query_params"]["年份"] = "{{未知}}"
        query.reset_mock()
        try:
            fetch_step_data(invalid, runtime)
        except ValueError:
            pass
        else:
            raise AssertionError("无效状态未被拒绝")
        query.assert_not_called()
    for metrics, values in [(["未配置指标"], before["slots"]),
                            (before["template"]["steps"][0]["metrics"], {**before["slots"], "月份": 9})]:
        try:
            fake(metrics, values)
        except DataQueryError:
            pass
        else:
            raise AssertionError("未配置的 Fake 请求应报错")
    for response in (None, {"value": object()}, {"value": float("nan")}):
        query.return_value = response
        try:
            fetch_step_data(state, runtime)
        except DataQueryError:
            pass
        else:
            raise AssertionError("无效查询响应未被拒绝")
    query.side_effect = DataQueryError("查询失败")
    previous = deepcopy(state)
    try:
        fetch_step_data(state, runtime)
    except DataQueryError:
        pass
    else:
        raise AssertionError("查询失败不能转为空数据")
    assert state == previous


if __name__ == "__main__":
    test_fetch_step_data()
    print("fetch_step_data: PASS")
