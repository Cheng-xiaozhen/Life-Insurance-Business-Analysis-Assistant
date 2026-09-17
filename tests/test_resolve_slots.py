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
from life_insurance_business_analysis_assistant.agent.graph import build_graph
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
    path = Path(__file__).resolve().parents[1] / "config/templates/Scenario/场景分析模板.yaml"
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
    assert state["slots"] == {"月份": 8, "渠道": "个险", "机构范围": "全系统"}
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

    invoke.side_effect = [
        {"values": {"月份": 8}, "ambiguous": {}},
        {"values": {"年份": 2026, "月份": 13}, "ambiguous": {}},
        {"values": {"月份": 9}, "ambiguous": {}},
    ]
    # 记录真实节点调用次数，确认补参不重新匹配或加载。
    import life_insurance_business_analysis_assistant.agent.graph as graph_module
    with patch.object(graph_module, "match_scenario", wraps=graph_module.match_scenario) as match, \
         patch.object(graph_module, "load_template", wraps=graph_module.load_template) as load:
        # MagicMock 不保留节点签名，用显式签名包装供 LangGraph 注入 runtime。
        def matching(state, runtime):
            return match(state, runtime)
        def loading(state, runtime):
            return load(state, runtime)
        with patch.object(graph_module, "match_scenario", matching), patch.object(graph_module, "load_template", loading):
            graph = build_graph()
        config = {"configurable": {"thread_id": "slots"}}
        result = graph.invoke(create_initial_state("8月标保"), config, context=context)
        assert result["__interrupt__"][0].value["kind"] == "slot_completion"
        for invalid in ("", 1):
            result = graph.invoke(Command(resume=invalid), config, context=context)
            assert "__interrupt__" in result
        result = graph.invoke(Command(resume="2026年，改成13月"), config, context=context)
        assert "月份" not in result["slots"] and "__interrupt__" in result
        result = graph.invoke(Command(resume="改成9月"), config, context=context)
        assert not result.get("__interrupt__")
        assert result["slots"]["年份"] == 2026 and result["slots"]["月份"] == 9
        assert result["question"] == "8月标保" and result["summary"] == "模拟场景总结"
        assert match.call_count == load.call_count == 1
        assert query.call_count == 5
        assert result["current_data"] is None
        assert result["step_results"][0]["data"]["is_mock"] is True
        assert result["step_index"] == 5 and len(result["step_results"]) == 5


if __name__ == "__main__":
    test_resolve_slots()
    print("resolve_slots: PASS")
