"""运行：python -B tests/test_summarize_scenario.py；不访问真实模型。"""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import Mock, patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from life_insurance_business_analysis_assistant.agent.context import AgentContext, load_scenario_catalog
from life_insurance_business_analysis_assistant.agent.graph import build_graph
from life_insurance_business_analysis_assistant.agent.nodes.load_template import load_template
from life_insurance_business_analysis_assistant.agent.nodes.summarize_scenario import summarize_scenario
from life_insurance_business_analysis_assistant.agent.state import AgentState, create_initial_state
from life_insurance_business_analysis_assistant.data_query import make_fake_query


@patch("life_insurance_business_analysis_assistant.agent.nodes.recommend_charts.get_llm")
@patch("life_insurance_business_analysis_assistant.agent.nodes.summarize_scenario.get_llm")
def test_summarize_scenario(get_llm, chart_llm):
    chart_model = Mock()
    chart_model.with_structured_output.return_value.invoke.return_value = {"recommended": False, "chart_type": None, "step_id": 1, "dimensions": [], "metrics": [], "reason": "数据不足", "description": "阅读结论"}
    chart_llm.return_value = chart_model
    path = Path(__file__).resolve().parents[1] / "config/templates/Scenario"
    slots = {"年份": 2026, "月份": 8, "渠道": "个险", "机构范围": "全系统"}
    state = create_initial_state("不传原始问题")
    state["scenario_id"] = "value_review"
    state.update(load_template(state, Runtime(context=AgentContext([], path))))
    state["slots"] = slots
    state["step_index"] = 3
    state["step_results"] = [{"step_id": i, "conclusion": f"模拟步骤结论{i}", "data_uses": [], "conclusion_step_ids": []} for i in (1, 2, 3)]
    state["datasets"] = {"test-secret": {"secret": "当前数据"}}
    before = deepcopy(state)
    model = Mock()
    model.stream_events.return_value = Mock(text=iter(["模拟场景", "总结"]), output=AIMessage(content="模拟场景总结"))
    get_llm.return_value = model
    assert summarize_scenario(state, {}) == {"summary": "模拟场景总结"}
    payload = json.loads(model.stream_events.call_args.args[0][1][1])
    assert set(payload) == {"scenario", "slots", "conclusions"}
    assert [c["step_id"] for c in payload["conclusions"]] == [1, 2, 3]
    assert "原始数据" not in str(payload) and "当前数据" not in str(payload)
    assert state == before
    for invalid in ("unfinished", "missing", "order", "empty"):
        candidate = deepcopy(state)
        if invalid == "unfinished": candidate["step_index"] = 2
        elif invalid == "missing": candidate["step_results"].pop()
        elif invalid == "order": candidate["step_results"].reverse()
        else: candidate["step_results"][0]["conclusion"] = " "
        get_llm.reset_mock()
        try:
            summarize_scenario(candidate, {})
        except ValueError:
            pass
        else:
            raise AssertionError("不完整步骤不应总结")
        get_llm.assert_not_called()
    for text, metadata in [(" ", {}), ("截断", {"finish_reason": "length"})]:
        model.stream_events.return_value = Mock(text=iter([text]), output=AIMessage(content=text, response_metadata=metadata))
        try:
            summarize_scenario(state, {})
        except RuntimeError:
            pass
        else:
            raise AssertionError("无效总结不应提交")
        assert state == before

    get_llm.return_value = FakeListChatModel(responses=["模拟场景总结"])
    graph = StateGraph(AgentState)
    graph.add_node("summarize_scenario", summarize_scenario)
    graph.add_edge(START, "summarize_scenario")
    graph.add_edge("summarize_scenario", END)
    stream = graph.compile().stream_events(state, version="v3")
    tokens = [token for message in stream.messages for token in message.text]
    assert len(tokens) > 1 and "".join(tokens) == stream.output["summary"]



if __name__ == "__main__":
    test_summarize_scenario()
    print("summarize_scenario: PASS")
