"""运行：python -B tests/test_resolve_slots.py；模型响应使用本地模拟。"""

from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from life_insurance_business_analysis_assistant.data_query import make_fake_query
from unittest.mock import MagicMock, patch

from langgraph.runtime import Runtime
from langgraph.types import Command

from life_insurance_business_analysis_assistant.agent.context import AgentContext, load_scenario_catalog
from life_insurance_business_analysis_assistant.agent.graph import build_analysis_graph
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.nodes.resolve_slots import resolve_slots
from life_insurance_business_analysis_assistant.agent.state import create_initial_state


@patch("life_insurance_business_analysis_assistant.agent.nodes.recommend_charts.get_llm")
@patch("life_insurance_business_analysis_assistant.agent.nodes.summarize_scenario.get_llm", return_value=FakeListChatModel(responses=["模拟场景总结"]))
@patch("life_insurance_business_analysis_assistant.agent.nodes.analyze_step.get_llm", return_value=FakeListChatModel(responses=["模拟数据分析结论"]))
@patch("life_insurance_business_analysis_assistant.agent.nodes.resolve_slots.get_llm")
def test_resolve_slots(get_llm, analysis_llm, summary_llm, chart_llm):
    chart_model = Mock()
    chart_model.with_structured_output.return_value.invoke.return_value = {"recommended": False, "chart_type": None, "step_id": 1, "dimensions": [], "metrics": [], "reason": "数据不足", "description": "阅读结论"}
    chart_llm.return_value = chart_model
    path = Path(__file__).resolve().parents[1] / "config/templates/Scenario"
    query = MagicMock(side_effect=make_fake_query({"年份": 2026, "月份": 9, "渠道": "个险", "机构范围": "全系统"}))
    context = AgentContext(load_scenario_catalog(path), path, query)
    model = MagicMock()
    get_llm.return_value = model
    invoke = model.with_structured_output.return_value.invoke
    state = create_initial_state("8月标保")
    state["scenario_id"] = "standard_premium_review"
    state.update(load_template(state, Runtime(context=context)))

    def resolve(values, ambiguous=None):
        invoke.return_value = {"values": values, "ambiguous": ambiguous or {}}
        before = deepcopy(state)
        update = resolve_slots(state)
        assert state == before
        state.update(update)
        assert state["user_reply"] is None

    resolve({"月份": 8})
    assert state["slots"] == {"月份": 8}
    assert {i["slot_name"] for i in state["clarification"]["slot_issues"]} == {"年份", "渠道", "机构范围"}
    resolve({"渠道": "个险"})
    assert state["clarification"]["slot_issues"][0]["slot_name"] == "年份"
    state["user_reply"] = "年份2026，机构不确定"
    resolve({"年份": 2026}, {"机构范围": "北京还是上海不确定"})
    assert "机构范围" not in state["slots"]
    resolve({"月份": 13})
    assert "月份" not in state["slots"] and "机构范围" not in state["slots"]
    resolve({"年份": 2025})
    assert len(state["clarification"]["slot_issues"]) == 2
    resolve({"月份": 9, "机构范围": "北京分公司"})
    assert state["clarification"] is None and state["slots"]["年份"] == 2025
    for value in (True, "8", 0, 13, None):
        resolve({"月份": value})
        assert "月份" not in state["slots"]
        assert state["clarification"]["slot_issues"][0]["reason"] == "invalid"
    for response in ({"values": {"阈值": 70}, "ambiguous": {}}, {"bad": 1}):
        invoke.return_value = response
        before = deepcopy(state)
        try:
            resolve_slots(state)
        except ValueError:
            pass
        else:
            raise AssertionError("未拒绝非法模型响应")
        assert state == before
    get_llm.return_value = None
    try:
        resolve_slots(state)
    except RuntimeError:
        pass
    else:
        raise AssertionError("未配置模型不应继续")
    get_llm.return_value = model

    from unittest import TestCase
    failure = ConnectionError("connection failed")
    failure.__cause__ = OSError("diagnostic root cause")
    invoke.side_effect = failure
    before = deepcopy(state)
    with TestCase().assertLogs(
        "life_insurance_business_analysis_assistant.agent.nodes.resolve_slots", level="ERROR"
    ) as captured:
        try:
            resolve_slots(state)
        except ConnectionError as exc:
            assert exc is failure
        else:
            raise AssertionError("模型调用失败必须原样抛出")
    assert "diagnostic root cause" in captured.output[0]
    assert state == before



if __name__ == "__main__":
    test_resolve_slots()
    print("resolve_slots: PASS")
