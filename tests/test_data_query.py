"""问数结构校验及 Mock 的真实适配边界，完全离线。"""
from workflow_support import execution_state
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock
from langgraph.runtime import Runtime
from life_insurance_business_analysis_assistant.agent.state import create_initial_state
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.subgraphs.analysis_execution.nodes.fetch_step_data import build_request
from life_insurance_business_analysis_assistant.data_query import DataQueryRequest, DataQueryError, validate_result
from life_insurance_business_analysis_assistant.mock_query_service import MockQueryService
from workflow_support import context, query_fixture


def test_data_query():
    state = create_initial_state("标保")
    state["scenario_id"] = "standard_premium_review"
    state.update(load_template(state, Runtime(context=context())))
    state = execution_state(state["template"], index=1)
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
    empty["datasets"][0]["notice"] = "查询成功，所述集合没有记录"
    assert validate_result(empty, request).datasets[0].rows == []
    partial = deepcopy(good)
    partial["datasets"][0]["rows"][0]["标保达成率"] = None
    partial["datasets"][0]["complete"] = False
    assert not validate_result(partial, request).datasets[0].complete
    for data in (empty, partial):
        data["datasets"][0]["notice"] = ""
        with TestCase().assertRaises(ValueError):
            validate_result(data, request)
    with TestCase().assertRaises(ValueError):
        DataQueryRequest.model_validate({**request.model_dump(), "slots": {"月份": 8}})
    model = Mock()
    invoke = model.with_structured_output.return_value.invoke
    response = deepcopy(good)
    response["datasets"][0]["notice"] = ""
    original = deepcopy(response)
    invoke.return_value = response
    result = MockQueryService(model)(request)
    assert result.model_dump() == original
    assert response == original  # 不修改模型返回对象或追加声明。
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
    print("query contracts, unchanged response, bounded retry and failure: PASS")


def test_pie_recommendation():
    from unittest.mock import patch
    from life_insurance_business_analysis_assistant.agent.nodes.recommend_charts import (
        ChartDecision, assemble_chart, chart_candidates, recommend_charts,
    )

    state = create_initial_state("机构标保构成")
    state["scenario_id"] = "standard_premium_review"
    state.update(load_template(state, Runtime(context=context())))
    state["template"]["steps"] = [{"step_id": 1, "text": "查看两个机构的标保构成", "metrics": ["标保"]}]
    data = {"dimensions": ["机构"], "metrics": ["标保"],
            "rows": [{"机构": "甲", "标保": 60}, {"机构": "乙", "标保": 40}],
            "units": {"标保": "万元"}, "complete": True,
            "notice": "机构范围为甲、乙，未指定年月。"}
    state["analysis_result"] = {
        "datasets": {"d1": {"step_id": 1, "request": {}, "payload": data}},
        "step_results": [{"step_id": 1, "dataset_ids": ["d1"], "conclusion": "甲60万元，乙40万元。"}],
    }
    state["summary"] = "两个机构的标保数据。"
    decision = ChartDecision(recommended=True, chart_type="pie", step_id=1, candidate_id="data-1",
                             dimensions=["机构"], metrics=["标保"],
                             reason="机构分类互斥，标保可加总为所示两个机构的合计。",
                             description="展示甲、乙两个机构的标保构成。")
    model = Mock()
    model.with_structured_output.return_value.invoke.return_value = {"recommendations": [decision.model_dump()]}
    with patch("life_insurance_business_analysis_assistant.agent.nodes.recommend_charts.get_llm", return_value=model):
        chart = recommend_charts(state, {})["chart_recommendations"][0]
    assert chart["recommended"] and chart["chart_type"] == "pie" and chart["data"] == data["rows"]
    assert chart["description"] == decision.description
    import json
    sent = json.loads(model.with_structured_output.return_value.invoke.call_args.args[0][1][1])
    assert sent["scenarioInfo"]["scenario_id"] == state["scenario_id"]
    assert sent["candidates"][0]["step"] == state["template"]["steps"][0]
    candidate = chart_candidates(state)[0]
    for values in ((-1, 40), (0, 0)):
        invalid = deepcopy(candidate)
        for row, value in zip(invalid["data"]["rows"], values):
            row["标保"] = value
        assert not assemble_chart(decision, invalid)["recommended"]
    for field, value in (("complete", False), ("units", {"标保": "%"})):
        invalid = deepcopy(candidate)
        invalid["data"][field] = value
        assert not assemble_chart(decision, invalid)["recommended"]
    print("pie without query hints, recommendation context and numeric guards: PASS")


if __name__ == "__main__":
    test_data_query()
    test_pie_recommendation()
