"""运行：python -B tests/test_recommend_charts.py；使用模拟模型决策。"""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.context import AgentContext
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.nodes.recommend_charts import ChartDecision, recommend_charts
from life_insurance_business_analysis_assistant.agent.state import create_initial_state


@patch("life_insurance_business_analysis_assistant.agent.nodes.recommend_charts.get_llm")
def test_recommend_charts(get_llm):
    path = Path(__file__).resolve().parents[1] / "config/templates/Scenario/场景分析模板.yaml"
    state = create_initial_state("标保")
    state["scenario_id"] = "standard_premium_review"
    state.update(load_template(state, Runtime(context=AgentContext([], path))))
    state["step_index"] = 5
    state["summary"] = "总结"
    state["step_results"] = [
        {"step_id": 1, "data": {"rows": [{"机构": "甲", "金额": 10}, {"机构": "乙", "金额": 20}]}, "conclusion": "首步结论"},
        {"step_id": 2, "data": {"secret": "后续数据"}, "conclusion": "后续结论"},
    ]
    model = Mock()
    get_llm.return_value = model
    invoke = model.with_structured_output.return_value.invoke
    decision = {"recommended": True, "chart_type": "bar", "step_id": 1,
                "dimensions": ["机构"], "metrics": ["金额"], "reason": "机构金额比较", "description": "比较两机构"}
    invoke.return_value = decision
    before = deepcopy(state)
    result = recommend_charts(state, {})
    assert result == {"chart_recommendations": [decision]}
    assert state == before
    prompt = invoke.call_args.args[0][0][1]
    assert json.loads(prompt.split("JSON Schema:\n", 1)[1]) == ChartDecision.model_json_schema()
    payload = json.loads(invoke.call_args.args[0][1][1])
    assert payload["available_fields"] == ["机构", "金额"]
    assert "后续数据" not in str(payload) and "后续结论" not in str(payload)
    for changes in ({"chart_type": "radar"}, {"step_id": 2}, {"metrics": ["不存在"]},
                    {"recommended": False}, {"reason": " "}, {"dimensions": []},
                    {"chart_type": "scatter"}, {"dimensions": ["金额"]}):
        invoke.return_value = {**decision, **changes}
        try:
            recommend_charts(state, {})
        except ValueError:
            pass
        else:
            raise AssertionError(f"非法决策未被拒绝: {changes}")
        assert state == before
    state["step_results"][0]["data"] = {"rows": [{"金额": 10}], "query_params": {"机构": "全系统"}}
    invoke.return_value = {**decision, "recommended": False, "chart_type": None,
                           "dimensions": [], "metrics": [], "reason": "单条总体记录", "description": "阅读结论"}
    assert recommend_charts(state, {})["chart_recommendations"][0]["recommended"] is False
    assert json.loads(invoke.call_args.args[0][1][1])["available_fields"] == ["金额"]
    state["step_results"][0]["data"] = {"rows": []}
    assert recommend_charts(state, {})["chart_recommendations"][0]["reason"] == "单条总体记录"
    invoke.side_effect = RuntimeError("模型失败")
    before = deepcopy(state)
    try:
        recommend_charts(state, {})
    except RuntimeError:
        pass
    else:
        raise AssertionError("不能将模型失败伪装为不推荐")
    assert state == before


if __name__ == "__main__":
    test_recommend_charts()
    print("recommend_charts: PASS")
