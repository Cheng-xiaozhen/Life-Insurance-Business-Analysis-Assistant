"""运行：python -B tests/test_graph.py。验证真实暂停恢复，无模型调用。"""

from pathlib import Path
from unittest.mock import Mock
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from life_insurance_business_analysis_assistant.data_query import make_fake_query
from unittest.mock import MagicMock, patch

from langgraph.types import Command

from life_insurance_business_analysis_assistant.agent.context import AgentContext, load_scenario_catalog
from life_insurance_business_analysis_assistant.agent.graph import build_graph
from life_insurance_business_analysis_assistant.agent.state import create_initial_state


@patch("life_insurance_business_analysis_assistant.agent.nodes.recommend_charts.get_llm")
@patch("life_insurance_business_analysis_assistant.agent.nodes.summarize_scenario.get_llm", return_value=FakeListChatModel(responses=["模拟场景总结"]))
@patch("life_insurance_business_analysis_assistant.agent.nodes.analyze_step.get_llm", return_value=FakeListChatModel(responses=["模拟数据分析结论"]))
@patch("life_insurance_business_analysis_assistant.agent.nodes.resolve_slots.get_llm")
def test_graph(get_llm, analysis_llm, summary_llm, chart_llm):
    chart_model = Mock()
    chart_model.with_structured_output.return_value.invoke.return_value = {"recommended": False, "chart_type": None, "step_id": 1, "dimensions": [], "metrics": [], "reason": "数据不足", "description": "阅读结论"}
    chart_llm.return_value = chart_model
    model = MagicMock()
    model.with_structured_output.return_value.invoke.return_value = {"values": {"年份": 2026, "月份": 8}, "ambiguous": {}}
    get_llm.return_value = model
    path = Path(__file__).resolve().parents[1] / "config/templates/Scenario/场景分析模板.yaml"
    query = MagicMock(side_effect=make_fake_query({"年份": 2026, "月份": 8, "渠道": "个险", "机构范围": "全系统"}))
    context = AgentContext(load_scenario_catalog(path), path, query)
    graph = build_graph()
    for thread, question, expected in [
        ("zero", "人力情况", None),
        ("single", "标保达成率", "standard_premium_review"),
    ]:
        config = {"configurable": {"thread_id": thread}}
        # 零命中不给文件路径：若误入加载节点就会报错。
        result = graph.invoke(create_initial_state(question), config,
                              context=context if expected else AgentContext(context.scenario_catalog))
        assert result["scenario_id"] == expected
        assert not result.get("__interrupt__")
        assert graph.get_state(config).next == ()
        assert (result["template"] is not None) == (expected is not None)

    configs = [{"configurable": {"thread_id": name}} for name in ("a", "b")]
    question = "2026年8月标保达成率和价值"
    for config in configs:
        result = graph.invoke(create_initial_state(question), config, context=context)
        payload = result["__interrupt__"][0].value
        assert payload["kind"] == "scenario_selection"
        assert [item["score"] for item in payload["candidates"]] == [3.0, 1.0]
        assert result["scenario_id"] is None and result["template"] is None
        assert graph.get_state(config).next == ("clarify",)

    for invalid in ("", "unknown", 1, ["value_review"]):
        result = graph.invoke(Command(resume=invalid), configs[0], context=context)
        assert "选择无效" in result["__interrupt__"][0].value["prompt"]
        assert result["scenario_id"] is None and result["template"] is None
        assert result["question"] == question

    result = graph.invoke(Command(resume="value_review"), configs[0], context=context)
    assert result["scenario_id"] == result["template"]["scenario_id"] == "value_review"
    assert result["clarification"] is None and result["question"] == question
    assert result["slots"]["月份"] == 8 and result["summary"] == "模拟场景总结"
    assert graph.get_state(configs[0]).next == ()
    # 另一个 thread 仍在暂停，随后可以独立选择不同场景。
    assert graph.get_state(configs[1]).next == ("clarify",)
    assert graph.get_state(configs[1]).values["scenario_id"] is None
    other = graph.invoke(Command(resume="standard_premium_review"), configs[1], context=context)
    assert other["template"]["scenario_id"] == "standard_premium_review"



if __name__ == "__main__":
    test_graph()
    print("graph interrupt/resume: PASS")
