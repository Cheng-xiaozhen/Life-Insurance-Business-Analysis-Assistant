"""问数结构校验及 Mock 的真实适配边界，完全离线。"""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock
from langgraph.runtime import Runtime
from life_insurance_business_analysis_assistant.agent.state import create_initial_state
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.nodes.fetch_step_data import build_request
from life_insurance_business_analysis_assistant.data_query import DataQueryRequest, DataQueryError, validate_result
from life_insurance_business_analysis_assistant.mock_query_service import MockQueryService
from workflow_support import context, query_fixture


def test_data_query():
    state = create_initial_state("标保")
    state["scenario_id"] = "standard_premium_review"
    state.update(load_template(state, Runtime(context=context())))
    state["step_index"] = 1
    request = build_request(state)
    good = query_fixture(request).model_dump()
    invalid = []
    for value in (True, "80%", float("nan"), float("inf"), None):
        data = deepcopy(good)
        data["datasets"][0]["rows"][0]["标保达成率"] = value
        invalid.append(data)
    for field, value in (("units", {}), ("time_dimensions", ["机构"]), ("metrics", ["新指标"]), ("extra", True)):
        data = deepcopy(good)
        data["datasets"][0][field] = value
        invalid.append(data)
    data = deepcopy(good)
    data["datasets"][0]["rows"].append(deepcopy(data["datasets"][0]["rows"][0]))
    invalid.append(data)
    for data in invalid:
        with TestCase().assertRaises(ValueError):
            validate_result(data, request)
    empty = deepcopy(good)
    empty["datasets"][0]["rows"] = []
    empty["datasets"][0]["notice"] = "查询成功，所述模拟集合没有记录"
    assert validate_result(empty, request).datasets[0].rows == []
    partial = deepcopy(good)
    partial["datasets"][0]["rows"][0]["标保达成率"] = None
    partial["datasets"][0]["complete"] = False
    assert not validate_result(partial, request).datasets[0].complete
    with TestCase().assertRaises(ValueError):
        DataQueryRequest.model_validate({**request.model_dump(), "slots": {"月份": 8}})
    model = Mock()
    invoke = model.with_structured_output.return_value.invoke
    fake_real = deepcopy(good)
    fake_real["datasets"][0]["is_mock"] = False
    invoke.return_value = fake_real
    result = MockQueryService(model)(request)
    assert result.datasets[0].is_mock and "独立步骤" in result.datasets[0].notice
    assert not fake_real["datasets"][0]["is_mock"]  # 不修改模型返回对象。
    assert "slots" not in invoke.call_args.args[0][1][1]
    assert invoke.call_args.kwargs["config"]["tags"]
    invoke.side_effect = [invalid[0], good]
    invoke.reset_mock()
    assert MockQueryService(model)(request).datasets
    assert invoke.call_count == 2
    invoke.side_effect = [invalid[0], invalid[0]]
    invoke.reset_mock()
    with TestCase().assertRaises(DataQueryError):
        MockQueryService(model)(request)
    assert invoke.call_count == 2
    invoke.side_effect = TimeoutError("超时")
    invoke.reset_mock()
    with TestCase().assertRaises(DataQueryError):
        MockQueryService(model)(request)
    assert invoke.call_count == 1
    with TestCase().assertRaises(DataQueryError):
        MockQueryService(None)(request)
    print("query contracts, mock identity, bounded retry and failure: PASS")

if __name__ == "__main__":
    test_data_query()
